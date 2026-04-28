from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from copilot_log_backend.application.config import BackendConfig

from .dependencies import get_config

bearer_scheme = HTTPBearer(auto_error=False)


def token_is_valid(token: str, config: BackendConfig) -> bool:
    return any(secrets.compare_digest(token, expected) for expected in config.api_keys)


def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    config: BackendConfig = Depends(get_config),
) -> BackendConfig:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not config.api_keys or not token_is_valid(credentials.credentials, config):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bearer token")
    return config
