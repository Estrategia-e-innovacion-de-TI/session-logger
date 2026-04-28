from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from copilot_log_backend.domain.entities.event import EventRecord, parse_timestamp


class EventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: parse_timestamp(None))
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
    created_at: datetime = Field(default_factory=lambda: parse_timestamp(None))

    @field_validator("timestamp", "created_at", mode="before")
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

    def to_domain(self) -> EventRecord:
        return EventRecord(
            event_id=self.event_id,
            session_id=self.session_id,
            event_type=self.event_type,
            timestamp=self.timestamp,
            user_prompt=self.user_prompt,
            prompt_hash=self.prompt_hash,
            repo_path=self.repo_path,
            repo_name=self.repo_name,
            git_branch=self.git_branch,
            git_commit=self.git_commit,
            working_directory=self.working_directory,
            actor=self.actor,
            files_changed=list(self.files_changed),
            tool_name=self.tool_name,
            command=self.command,
            status=self.status,
            error=self.error,
            raw_payload=self.raw_payload,
            metadata=dict(self.metadata),
            created_at=self.created_at,
        )


class BatchEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[dict[str, Any]]
