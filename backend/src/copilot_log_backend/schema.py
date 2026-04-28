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
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise TypeError(f"Unsupported timestamp value: {value!r}")


def compute_prompt_hash(prompt: str | None) -> str | None:
    if prompt is None:
        return None
    return sha256(prompt.encode("utf-8")).hexdigest()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


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
    def validate_event_type_present(cls, value: str) -> str:
        if not value:
            raise ValueError("event_type is required")
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


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[dict[str, Any]]


def validate_event_type_allowed(event_type: str, *, allow_unknown: bool) -> None:
    if allow_unknown or event_type in SUPPORTED_EVENTS:
        return
    raise ValueError(f"Unsupported event_type: {event_type}")
