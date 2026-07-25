import json
import logging
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any, Final

from app.core.config import Settings

REQUEST_ID_CONTEXT: ContextVar[str | None] = ContextVar("request_id", default=None)

LOG_RECORD_FIELDS: Final = {
    "event",
    "request_id",
    "environment",
    "method",
    "endpoint",
    "status_code",
    "duration_ms",
    "error_type",
    "sentry_enabled",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }
        request_id = getattr(record, "request_id", None) or REQUEST_ID_CONTEXT.get()
        if request_id is not None:
            payload["request_id"] = request_id
        for field in LOG_RECORD_FIELDS - {"event", "request_id"}:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        request_id = getattr(record, "request_id", None) or REQUEST_ID_CONTEXT.get() or "-"
        event = getattr(record, "event", record.getMessage())
        return f"{record.levelname:<7} request_id={request_id} {event}"


def configure_logging(settings: Settings) -> logging.Logger:
    # Uvicorn's default access log includes the raw query string. The structured
    # request log below replaces it with a bounded endpoint identifier.
    logging.getLogger("uvicorn.access").disabled = True
    logger = logging.getLogger("nutripilot")
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if settings.log_format == "json" else ConsoleFormatter())
    logger.addHandler(handler)
    logger.setLevel(settings.log_level)
    logger.propagate = False
    return logger


def bind_request_id(request_id: str) -> Token[str | None]:
    return REQUEST_ID_CONTEXT.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    REQUEST_ID_CONTEXT.reset(token)
