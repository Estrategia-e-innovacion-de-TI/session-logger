from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.domain.model.copilot_event import CopilotEvent, parse_timestamp


class EventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: parse_timestamp(None))
    user_id: str | None = None
    source: str | None = None
    repository: str | None = None
    branch: str | None = None
    workspace: str | None = None
    mode: str | None = None
    execution_mode: str | None = None
    invocation_origin: str | None = None
    user_prompt_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("userPrompt_id", "user_prompt_id"),
        serialization_alias="userPrompt_id",
    )
    parent_user_prompt_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("parent_userPrompt_id", "parent_user_prompt_id"),
        serialization_alias="parent_userPrompt_id",
    )
    tool_name: str | None = None
    prompt_text: str | None = None
    assistant_response_summary: str | None = None
    tool_input_summary: str | None = None
    tool_result_summary: str | None = None
    status: str | None = None
    duration_ms: int | None = None
    files_touched: list[str] = Field(default_factory=list)
    files_added: list[str] = Field(default_factory=list)
    commands_executed: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_payload: Any = None
    created_at: datetime = Field(default_factory=lambda: parse_timestamp(None))

    user_prompt: str | None = None
    repo_name: str | None = None
    repo_path: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    working_directory: str | None = None
    actor: str | None = None
    files_changed: list[str] = Field(default_factory=list)
    command: str | None = None
    error: str | None = None

    @field_validator("timestamp", "created_at", mode="before")
    @classmethod
    def normalize_timestamp(cls, value: Any) -> datetime:
        return parse_timestamp(value)

    @field_validator("files_touched", "files_added", "commands_executed", "files_changed", mode="before")
    @classmethod
    def normalize_string_list(cls, value: Any) -> list[str]:
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

    def to_domain(self) -> CopilotEvent:
        commands = list(self.commands_executed)
        if self.command:
            commands.append(self.command)
        metadata = dict(self.metadata)
        if self.source:
            metadata["source"] = self.source
        if self.error and "error" not in metadata:
            metadata["error"] = self.error
        if self.repo_path and "repo_path" not in metadata:
            metadata["repo_path"] = self.repo_path
        if self.git_commit and "git_commit" not in metadata:
            metadata["git_commit"] = self.git_commit
        if self.mode:
            metadata["mode"] = self.mode
        if self.execution_mode:
            metadata["execution_mode"] = self.execution_mode
        if self.invocation_origin:
            metadata["invocation_origin"] = self.invocation_origin
        return CopilotEvent(
            event_id=self.event_id,
            session_id=self.session_id,
            event_type=self.event_type,
            timestamp=self.timestamp,
            user_id=self.user_id or self.actor,
            repository=self.repository or self.repo_name,
            branch=self.branch or self.git_branch,
            workspace=self.workspace or self.working_directory,
            user_prompt_id=self.user_prompt_id,
            parent_user_prompt_id=self.parent_user_prompt_id,
            tool_name=self.tool_name,
            prompt_text=self.prompt_text or self.user_prompt,
            assistant_response_summary=self.assistant_response_summary,
            tool_input_summary=self.tool_input_summary,
            tool_result_summary=self.tool_result_summary,
            status=self.status,
            duration_ms=self.duration_ms,
            files_touched=self.files_touched or self.files_changed,
            files_added=self.files_added,
            commands_executed=commands,
            metadata=metadata,
            raw_payload=self.raw_payload,
            created_at=self.created_at,
        )


class BatchEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[dict[str, Any]]
