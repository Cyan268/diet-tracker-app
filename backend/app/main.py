import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import dispose_engine
from app.core.logging import configure_logging
from app.core.observability import (
    RequestObservabilityMiddleware,
    initialize_error_monitoring,
    unhandled_exception_handler,
)
from app.core.redis import close_redis_client
from app.services.demo_reset import run_demo_reset_loop
from app.web import create_spa_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    reset_task: asyncio.Task[None] | None = None
    if settings.demo_reset_interval_minutes > 0:
        reset_task = asyncio.create_task(run_demo_reset_loop(settings), name="demo-reset")
    try:
        yield
    finally:
        if reset_task is not None:
            reset_task.cancel()
            with suppress(asyncio.CancelledError):
                await reset_task
        await close_redis_client()
        await dispose_engine()


settings = get_settings()
application_logger = configure_logging(settings)
sentry_enabled = initialize_error_monitoring(settings)
application_logger.info(
    "application.configured",
    extra={
        "event": "application.configured",
        "environment": settings.environment,
        "sentry_enabled": sentry_enabled,
    },
)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.effective_allowed_hosts)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.add_middleware(RequestObservabilityMiddleware, environment=settings.environment)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(api_router, prefix=settings.api_v1_prefix)


if settings.web_dist_dir is not None:
    app.include_router(create_spa_router(settings.web_dist_dir, api_prefix=settings.api_v1_prefix))
else:

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "docs": "/docs",
            "health": f"{settings.api_v1_prefix}/health/live",
        }
