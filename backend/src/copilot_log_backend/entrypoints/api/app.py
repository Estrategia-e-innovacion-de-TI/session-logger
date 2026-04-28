from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from copilot_log_backend.application.config import BackendConfig, load_config
from copilot_log_backend.application.container import ApplicationContainer

from .routes import events, health


def create_app(config: BackendConfig | None = None) -> FastAPI:
    app_config = config or load_config()
    container = ApplicationContainer(app_config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app_config.storage == "postgres" and app_config.auto_migrate:
            _ = container.repository
        yield

    app = FastAPI(title="Copilot Log Backend", version="0.1.0", lifespan=lifespan)
    app.state.config = app_config
    app.state.container = container

    @app.middleware("http")
    async def reject_large_bodies(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                body_size = int(content_length)
            except ValueError:
                body_size = 0
            if body_size > app_config.max_body_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Request body too large"},
                )
        return await call_next(request)

    app.include_router(health.router)
    app.include_router(events.router)
    return app
