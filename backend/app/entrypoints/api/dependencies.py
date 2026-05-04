from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.dependency_injection import DependencyContainer
from app.config.settings import BackendSettings

bearer_scheme = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> BackendSettings:
    return request.app.state.settings


def get_container(request: Request) -> DependencyContainer:
    return request.app.state.container


def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_logger_token: str | None = Header(default=None, alias="X-Logger-Token"),
    container: DependencyContainer = Depends(get_container),
) -> None:
    token = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif x_logger_token:
        token = x_logger_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token or X-Logger-Token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not container.settings.api_keys or not container.api_key_validator.is_valid(token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bearer token")
