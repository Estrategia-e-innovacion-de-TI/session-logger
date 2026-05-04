from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/copilot_logs"


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def parse_positive_float(value: Any, default: float) -> float:
    if value in (None, ""):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def parse_positive_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


@dataclass(frozen=True, slots=True)
class BackendSettings:
    api_keys: tuple[str, ...]
    database_url: str
    max_body_mb: float
    allow_unknown_event_types: bool
    query_limit: int
    analytics_limit: int
    auto_migrate: bool = True
    log_level: str = "INFO"

    @property
    def max_body_bytes(self) -> int:
        return int(self.max_body_mb * 1024 * 1024)


def load_settings(env: Mapping[str, str] | None = None) -> BackendSettings:
    env = dict(env or os.environ)
    allow_unknown = (
        env.get("COPILOT_LOG_BACKEND_ALLOW_UNKNOWN_EVENT_TYPES")
        if "COPILOT_LOG_BACKEND_ALLOW_UNKNOWN_EVENT_TYPES" in env
        else env.get("ALLOW_UNKNOWN_EVENT_TYPES")
    )
    query_limit = parse_positive_int(env.get("COPILOT_LOG_BACKEND_QUERY_LIMIT"), 100)
    return BackendSettings(
        api_keys=_parse_api_keys(env.get("COPILOT_LOG_BACKEND_API_KEYS")),
        database_url=env.get("COPILOT_LOG_BACKEND_DATABASE_URL", DEFAULT_DATABASE_URL),
        max_body_mb=parse_positive_float(env.get("COPILOT_LOG_BACKEND_MAX_BODY_MB"), 2),
        allow_unknown_event_types=parse_bool(allow_unknown, default=False),
        query_limit=query_limit,
        analytics_limit=parse_positive_int(env.get("COPILOT_LOG_BACKEND_ANALYTICS_LIMIT"), query_limit),
        auto_migrate=parse_bool(env.get("COPILOT_LOG_BACKEND_AUTO_MIGRATE"), default=True),
        log_level=env.get("COPILOT_LOG_BACKEND_LOG_LEVEL", "INFO"),
    )


def _parse_api_keys(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(key.strip() for key in value.split(",") if key.strip())

