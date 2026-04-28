from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SUPPORTED_EVENTS = (
    "sessionStart",
    "userPromptSubmitted",
    "preToolUse",
    "postToolUse",
    "sessionEnd",
    "errorOccurred",
)

PROMPT_PATHS = (
    ("prompt",),
    ("userPrompt",),
    ("message",),
    ("input",),
    ("text",),
    ("initialPrompt",),
    ("request", "prompt"),
    ("payload", "prompt"),
)

SESSION_ID_PATHS = (
    ("session_id",),
    ("sessionId",),
    ("invocation", "sessionId"),
    ("payload", "sessionId"),
)

ACTOR_PATHS = (
    ("actor",),
    ("user",),
    ("username",),
    ("invocation", "user"),
    ("payload", "actor"),
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: Any) -> datetime:
    if value is None or value == "":
        return utc_now()
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number = number / 1000.0
        return datetime.fromtimestamp(number, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return utc_now()
        if text.isdigit():
            return parse_timestamp(int(text))
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    raise TypeError(f"Unsupported timestamp value: {value!r}")


def compute_prompt_hash(prompt: str | None) -> str | None:
    if prompt is None:
        return None
    return sha256(prompt.encode("utf-8")).hexdigest()


def maybe_parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "{[":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def deep_get(payload: Any, path: tuple[str, ...]) -> Any:
    current = payload
    for segment in path:
        current = maybe_parse_json(current)
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def first_value(payload: Any, paths: tuple[tuple[str, ...], ...]) -> Any:
    for path in paths:
        value = deep_get(payload, path)
        if value not in (None, ""):
            return value
    return None


def stringify_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    event_type: str
    timestamp: datetime = Field(default_factory=utc_now)
    user_prompt: str | None = None
    prompt_hash: str | None = None
    repo_path: str | None = None
    repo_name: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    working_directory: str | None = None
    actor: str | None = None
    files_changed: list[str] = Field(default_factory=list)
    tool_name: str | None = None
    command: str | None = None
    status: str | None = None
    error: str | None = None
    raw_payload: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        if value not in SUPPORTED_EVENTS:
            raise ValueError(f"Unsupported event_type: {value}")
        return value

    @field_validator("timestamp", mode="before")
    @classmethod
    def normalize_timestamp(cls, value: Any) -> datetime:
        return parse_timestamp(value)

    @field_validator("files_changed", mode="before")
    @classmethod
    def normalize_files_changed(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @field_validator("metadata", mode="before")
    @classmethod
    def normalize_metadata(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        return {"value": value}

    @model_validator(mode="after")
    def ensure_prompt_hash(self) -> "EventRecord":
        self.prompt_hash = compute_prompt_hash(self.user_prompt)
        return self

    def to_jsonable(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

