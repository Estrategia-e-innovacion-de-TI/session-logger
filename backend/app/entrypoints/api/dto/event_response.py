from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.domain.model.copilot_event import CopilotEvent
from app.domain.model.session import Session
from app.domain.model.user_prompt import UserPrompt
from app.usecase.ingest_batch_events_usecase import BatchIngestResult


class EventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    event_id: str
    session_id: str
    event_type: str
    timestamp: datetime
    user_id: str | None = None
    actor: str | None = None
    source: str | None = None
    repository: str | None = None
    branch: str | None = None
    workspace: str | None = None
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
    files_touched: list[str]
    commands_executed: list[str]
    metadata: dict[str, Any]
    raw_payload: Any = None
    created_at: datetime

    @classmethod
    def from_domain(cls, event: CopilotEvent) -> "EventResponse":
        data = event.to_dict()
        data["actor"] = event.user_id
        data["source"] = event.metadata.get("source")
        return cls(**data)


class EventAcceptedResponse(BaseModel):
    status: str
    event_id: str
    created: bool
    event: EventResponse


class BatchErrorResponse(BaseModel):
    index: int
    event_id: str | None
    error: str


class BatchIngestResponse(BaseModel):
    accepted: int
    rejected: int
    created: int
    duplicated: int
    errors: list[BatchErrorResponse]

    @classmethod
    def from_result(cls, result: BatchIngestResult) -> "BatchIngestResponse":
        return cls(
            accepted=result.accepted,
            rejected=result.rejected,
            created=result.created,
            duplicated=result.duplicated,
            errors=[
                BatchErrorResponse(index=error.index, event_id=error.event_id, error=error.error)
                for error in result.errors
            ],
        )


class QueryEventsResponse(BaseModel):
    count: int
    events: list[EventResponse]

    @classmethod
    def from_events(cls, events: list[CopilotEvent]) -> "QueryEventsResponse":
        return cls(count=len(events), events=[EventResponse.from_domain(event) for event in events])


class SessionTraceResponse(BaseModel):
    session_id: str
    event_count: int
    repositories: list[str]
    first_event_at: datetime | None
    last_event_at: datetime | None
    events: list[EventResponse]

    @classmethod
    def from_domain(cls, session: Session) -> "SessionTraceResponse":
        return cls(
            session_id=session.session_id,
            event_count=len(session.events),
            repositories=session.repositories,
            first_event_at=session.first_event_at,
            last_event_at=session.last_event_at,
            events=[EventResponse.from_domain(event) for event in session.events],
        )


class PromptTraceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_prompt_id: str = Field(serialization_alias="userPrompt_id")
    session_id: str | None = None
    prompt_text: str | None = None
    parent_user_prompt_id: str | None = Field(default=None, serialization_alias="parent_userPrompt_id")
    event_count: int
    events: list[EventResponse]

    @classmethod
    def from_domain(cls, prompt: UserPrompt) -> "PromptTraceResponse":
        return cls(
            user_prompt_id=prompt.user_prompt_id,
            session_id=prompt.session_id,
            prompt_text=prompt.prompt_text,
            parent_user_prompt_id=prompt.parent_user_prompt_id,
            event_count=len(prompt.events),
            events=[EventResponse.from_domain(event) for event in prompt.events],
        )
