import logging
import re
from time import perf_counter
from typing import Any, Final
from uuid import uuid4

import sentry_sdk
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.logging import bind_request_id, reset_request_id

REQUEST_ID_HEADER: Final = b"x-request-id"
REQUEST_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
logger = logging.getLogger("nutripilot.http")


def normalize_request_id(value: str | None) -> str:
    if value is not None and REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return uuid4().hex


def _request_id_from_scope(scope: Scope) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == REQUEST_ID_HEADER:
            try:
                return normalize_request_id(value.decode("ascii"))
            except UnicodeDecodeError:
                break
    return normalize_request_id(None)


def _endpoint_name(scope: Scope) -> str:
    endpoint = scope.get("endpoint")
    module = getattr(endpoint, "__module__", None)
    name = getattr(endpoint, "__name__", None)
    if isinstance(module, str) and isinstance(name, str):
        return f"{module}.{name}"
    return "unmatched"


def _log_level(status_code: int) -> int:
    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO


class RequestObservabilityMiddleware:
    def __init__(self, app: ASGIApp, environment: str) -> None:
        self.app = app
        self.environment = environment

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id_from_scope(scope)
        scope.setdefault("state", {})["request_id"] = request_id
        token = bind_request_id(request_id)
        started_at = perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != REQUEST_ID_HEADER
                ]
                headers.append((REQUEST_ID_HEADER, request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = max(round((perf_counter() - started_at) * 1000), 0)
            logger.log(
                _log_level(status_code),
                "request.completed",
                extra={
                    "event": "request.completed",
                    "request_id": request_id,
                    "environment": self.environment,
                    "method": scope.get("method", "unknown"),
                    "endpoint": _endpoint_name(scope),
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            reset_request_id(token)


def scrub_sentry_event(event: dict[str, Any], _: dict[str, Any]) -> dict[str, Any]:
    event.pop("user", None)
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        request.pop("env", None)
        request.pop("headers", None)
        request.pop("query_string", None)
        request.pop("url", None)
    return event


def initialize_error_monitoring(settings: Settings) -> bool:
    if settings.sentry_dsn is None:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment,
        release=settings.release,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=scrub_sentry_event,
    )
    return True


async def unhandled_exception_handler(request: Request, error: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", normalize_request_id(None))
    logger.error(
        "request.unhandled_exception",
        extra={
            "event": "request.unhandled_exception",
            "request_id": request_id,
            "method": request.method,
            "endpoint": _endpoint_name(request.scope),
            "status_code": 500,
            "error_type": type(error).__name__,
        },
    )
    sentry_sdk.capture_exception(error, tags={"request_id": request_id})
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error", "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )
