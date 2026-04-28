from __future__ import annotations

from fastapi import Request

from copilot_log_backend.application.config import BackendConfig
from copilot_log_backend.application.container import ApplicationContainer


def get_config(request: Request) -> BackendConfig:
    return request.app.state.config


def get_container(request: Request) -> ApplicationContainer:
    return request.app.state.container
