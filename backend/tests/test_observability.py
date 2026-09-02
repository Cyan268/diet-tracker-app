import json
import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logging import JsonFormatter, configure_logging
from app.core.observability import (
    RequestObservabilityMiddleware,
    initialize_error_monitoring,
    normalize_request_id,
    scrub_sentry_event,
    unhandled_exception_handler,
)


class RecordCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def log_collector() -> Iterator[RecordCollector]:
    logger = logging.getLogger("nutripilot.http")
    collector = RecordCollector()
    logger.addHandler(collector)
    yield collector
    logger.removeHandler(collector)


def observed_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestObservabilityMiddleware, environment="test")
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @app.get("/fail")
    async def fail() -> None:
        raise RuntimeError("api-key-secret-must-not-enter-logs")

    return app


def test_json_formatter_only_serializes_allowlisted_fields() -> None:
    record = logging.LogRecord(
        name="nutripilot.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message-secret",
        args=(),
        exc_info=None,
    )
    record.event = "safe.event"
    record.request_id = "request-12345678"
    record.authorization = "Bearer token-secret"
    record.api_key = "sk-secret"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "safe.event"
    assert payload["request_id"] == "request-12345678"
    assert "authorization" not in payload
    assert "api_key" not in payload
    assert "secret" not in json.dumps(payload)


def test_request_middleware_reuses_valid_id_and_logs_bounded_endpoint(
    log_collector: RecordCollector,
) -> None:
    request_id = "web-request-1234"
    with TestClient(observed_app()) as client:
        response = client.get(
            "/items/private-item-id?api_key=query-secret",
            headers={"X-Request-ID": request_id, "Authorization": "Bearer header-secret"},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    completed = next(
        record for record in log_collector.records if record.event == "request.completed"
    )
    assert completed.request_id == request_id
    assert completed.endpoint.endswith(".item")
    assert completed.status_code == 200
    assert "secret" not in completed.getMessage()


def test_unhandled_error_is_sanitized_and_keeps_trace_id(
    log_collector: RecordCollector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[Exception, dict[str, object]]] = []
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.capture_exception",
        lambda error, **kwargs: captured.append((error, kwargs)),
    )
    with TestClient(observed_app(), raise_server_exceptions=False) as client:
        response = client.get("/fail", headers={"X-Request-ID": "short"})

    assert response.status_code == 500
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    assert response.json() == {"detail": "internal server error", "request_id": request_id}
    error_record = next(
        record for record in log_collector.records if record.event == "request.unhandled_exception"
    )
    assert error_record.error_type == "RuntimeError"
    assert "api-key-secret" not in error_record.getMessage()
    assert len(captured) == 1
    assert captured[0][1]["tags"] == {"request_id": request_id}


def test_configured_logging_disables_raw_uvicorn_access_log() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    original_disabled = access_logger.disabled
    try:
        configure_logging(Settings(_env_file=None, environment="test"))
        assert access_logger.disabled is True
    finally:
        access_logger.disabled = original_disabled


def test_request_id_rejects_log_injection_characters() -> None:
    generated = normalize_request_id("valid-looking\nforged-log")
    assert len(generated) == 32
    assert generated.isalnum()


def test_sentry_scrubber_removes_request_and_user_data() -> None:
    event = {
        "user": {"id": "private-user"},
        "request": {
            "method": "POST",
            "url": "https://api.example/logs/private-id?token=secret",
            "headers": {"authorization": "Bearer secret"},
            "cookies": {"session": "secret"},
            "query_string": "token=secret",
            "data": {"food": "private meal"},
            "env": {"REMOTE_ADDR": "127.0.0.1"},
        },
    }

    scrubbed = scrub_sentry_event(event, {})

    assert "user" not in scrubbed
    assert scrubbed["request"] == {"method": "POST"}


def test_sentry_is_opt_in_and_uses_privacy_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    assert initialize_error_monitoring(Settings(_env_file=None)) is False
    options: dict[str, object] = {}
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.init", lambda **kwargs: options.update(kwargs)
    )
    settings = Settings(
        _env_file=None,
        environment="test",
        sentry_dsn="https://public@example.ingest.sentry.io/1",
        sentry_traces_sample_rate=0.25,
        release="nutripilot-api@0.1.0",
    )

    assert initialize_error_monitoring(settings) is True
    assert options["send_default_pii"] is False
    assert options["include_local_variables"] is False
    assert options["max_request_body_size"] == "never"
    assert options["traces_sample_rate"] == 0.25
    assert options["before_send"] is scrub_sentry_event
