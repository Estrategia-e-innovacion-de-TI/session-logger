from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict

DEFAULT_HOME_DIR = Path("~/.copilot-log-backend").expanduser()
DEFAULT_MAX_BODY_MB = 2


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


class BackendConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    api_keys: tuple[str, ...]
    storage: str = "jsonl"
    home_dir: Path = DEFAULT_HOME_DIR
    max_body_mb: float = DEFAULT_MAX_BODY_MB
    allow_unknown_event_types: bool = False

    @property
    def max_body_bytes(self) -> int:
        return int(self.max_body_mb * 1024 * 1024)

    @property
    def events_dir(self) -> Path:
        return self.home_dir / "events"

    @property
    def sqlite_path(self) -> Path:
        return self.home_dir / "events.db"

    def ensure_home(self) -> None:
        self.home_dir.mkdir(parents=True, exist_ok=True)
        if self.storage == "jsonl":
            self.events_dir.mkdir(parents=True, exist_ok=True)
        if self.storage == "sqlite":
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)


def _parse_api_keys(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(key.strip() for key in value.split(",") if key.strip())


def load_config(env: Mapping[str, str] | None = None) -> BackendConfig:
    env = dict(env or os.environ)
    storage = env.get("COPILOT_LOG_BACKEND_STORAGE", "jsonl").strip().lower()
    if storage not in {"jsonl", "sqlite"}:
        storage = "jsonl"
    allow_unknown = (
        env.get("COPILOT_LOG_BACKEND_ALLOW_UNKNOWN_EVENT_TYPES")
        if "COPILOT_LOG_BACKEND_ALLOW_UNKNOWN_EVENT_TYPES" in env
        else env.get("ALLOW_UNKNOWN_EVENT_TYPES")
    )
    return BackendConfig(
        api_keys=_parse_api_keys(env.get("COPILOT_LOG_BACKEND_API_KEYS")),
        storage=storage,
        home_dir=Path(env.get("COPILOT_LOG_BACKEND_HOME", str(DEFAULT_HOME_DIR))).expanduser(),
        max_body_mb=parse_positive_float(env.get("COPILOT_LOG_BACKEND_MAX_BODY_MB"), DEFAULT_MAX_BODY_MB),
        allow_unknown_event_types=parse_bool(allow_unknown, default=False),
    )
