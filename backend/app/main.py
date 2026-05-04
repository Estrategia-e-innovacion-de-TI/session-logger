from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.config.dependency_injection import DependencyContainer
from app.config.settings import BackendSettings, load_settings
from app.driven_adapters.observability.logger import configure_logging
from app.entrypoints.api.v1 import analytics_controller, events_controller, health_controller


def create_app(
    settings: BackendSettings | None = None,
    container: DependencyContainer | None = None,
) -> FastAPI:
    app_settings = settings or load_settings()
    configure_logging(app_settings.log_level)
    app_container = container or DependencyContainer(app_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app_settings.auto_migrate:
            _ = app_container.event_repository
        yield

    app = FastAPI(title="Copilot Session Logger API", version="0.2.0", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.container = app_container

    @app.middleware("http")
    async def reject_large_bodies(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                body_size = int(content_length)
            except ValueError:
                body_size = 0
            if body_size > app_settings.max_body_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Request body too large"},
                )
        return await call_next(request)

    app.include_router(health_controller.router)
    app.include_router(events_controller.router)
    app.include_router(analytics_controller.router)
    return app


app = create_app()

