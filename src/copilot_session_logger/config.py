from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_HOME_DIR = Path("~/.copilot-session-logger").expanduser()


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


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    jsonl_enabled: bool = True
    sqlite_enabled: bool = False


class AppConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    home_dir: Path
    logs_dir: Path
    sqlite_path: Path
    session_state_path: Path
    storage: StorageConfig = Field(default_factory=StorageConfig)
    actor: str | None = None
    dry_run: bool = False
    redact_secrets: bool = True
    config_path: Path | None = None

    def ensure_home(self) -> None:
        self.home_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.session_state_path.parent.mkdir(parents=True, exist_ok=True)
        if self.storage.sqlite_enabled:
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)


def _deep_get(mapping: Mapping[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _load_yaml_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _resolve_home_dir(
    env: Mapping[str, str],
    explicit_config_path: Path | None,
) -> Path:
    home_from_env = env.get("COPILOT_SESSION_LOGGER_HOME")
    if home_from_env:
        return Path(home_from_env).expanduser()

    if explicit_config_path and explicit_config_path.exists():
        config_data = _load_yaml_config(explicit_config_path)
        configured_home = _deep_get(config_data, ("paths", "home_dir")) or config_data.get("home_dir")
        if configured_home:
            return Path(str(configured_home)).expanduser()

    return DEFAULT_HOME_DIR


def load_config(
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> AppConfig:
    env = dict(env or os.environ)
    explicit_config_path = Path(config_path).expanduser() if config_path else None
    home_dir = _resolve_home_dir(env, explicit_config_path)

    if explicit_config_path is not None:
        resolved_config_path = explicit_config_path
    elif env.get("COPILOT_SESSION_LOGGER_CONFIG"):
        resolved_config_path = Path(env["COPILOT_SESSION_LOGGER_CONFIG"]).expanduser()
    else:
        resolved_config_path = home_dir / "config.yaml"
    config_data = _load_yaml_config(resolved_config_path)

    logs_dir_value = (
        env.get("COPILOT_SESSION_LOGGER_LOGS_DIR")
        or _deep_get(config_data, ("paths", "logs_dir"))
        or config_data.get("logs_dir")
        or str(home_dir / "logs")
    )
    sqlite_path_value = (
        env.get("COPILOT_SESSION_LOGGER_SQLITE_PATH")
        or _deep_get(config_data, ("paths", "sqlite_path"))
        or config_data.get("sqlite_path")
        or str(home_dir / "session_logs.db")
    )
    session_state_path_value = (
        _deep_get(config_data, ("paths", "session_state_path"))
        or config_data.get("session_state_path")
        or str(home_dir / "state" / "active_sessions.json")
    )
    sqlite_enabled_value = (
        env.get("COPILOT_SESSION_LOGGER_SQLITE_ENABLED")
        if "COPILOT_SESSION_LOGGER_SQLITE_ENABLED" in env
        else _deep_get(config_data, ("storage", "sqlite_enabled"))
    )
    jsonl_enabled_value = (
        env.get("COPILOT_SESSION_LOGGER_JSONL_ENABLED")
        if "COPILOT_SESSION_LOGGER_JSONL_ENABLED" in env
        else _deep_get(config_data, ("storage", "jsonl_enabled"))
    )
    dry_run_value = env.get("COPILOT_SESSION_LOGGER_DRY_RUN", config_data.get("dry_run"))
    actor_value = (
        env.get("COPILOT_SESSION_LOGGER_ACTOR")
        or config_data.get("actor")
        or env.get("GITHUB_ACTOR")
        or env.get("GITHUB_USER")
        or env.get("USER")
        or env.get("USERNAME")
    )
    redact_value = env.get("COPILOT_SESSION_LOGGER_REDACT_SECRETS", config_data.get("redact_secrets"))

    app_config = AppConfig(
        home_dir=home_dir,
        logs_dir=Path(str(logs_dir_value)).expanduser(),
        sqlite_path=Path(str(sqlite_path_value)).expanduser(),
        session_state_path=Path(str(session_state_path_value)).expanduser(),
        storage=StorageConfig(
            jsonl_enabled=parse_bool(jsonl_enabled_value, default=True),
            sqlite_enabled=parse_bool(sqlite_enabled_value, default=False),
        ),
        actor=actor_value,
        dry_run=parse_bool(dry_run_value, default=False),
        redact_secrets=parse_bool(redact_value, default=True),
        config_path=resolved_config_path if resolved_config_path.exists() else None,
    )
    return app_config


def load_session_index(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    sessions = data.get("sessions", data)
    return sessions if isinstance(sessions, dict) else {}


def save_session_index(path: Path, sessions: Mapping[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"sessions": dict(sessions)}
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
