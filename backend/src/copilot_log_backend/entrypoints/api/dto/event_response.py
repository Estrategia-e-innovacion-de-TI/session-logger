from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from copilot_log_backend.domain.entities.event import EventRecord
from copilot_log_backend.usecases.ingest_event_batch import BatchIngestResult


class EventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    session_id: str
    event_type: str
    timestamp: datetime
    user_prompt: str | None = None
    prompt_hash: str | None = None
    repo_path: str | None = None
    repo_name: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    working_directory: str | None = None
    actor: str | None = None
    files_changed: list[str]
    tool_name: str | None = None
    command: str | None = None
    status: str | None = None
    error: str | None = None
    raw_payload: Any = None
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_domain(cls, event: EventRecord) -> "EventResponse":
        return cls(**event.to_dict())


class EventAcceptedResponse(BaseModel):
    status: str
    event_id: str
    event: EventResponse


class BatchErrorResponse(BaseModel):
    index: int
    event_id: str | None
    error: str


class BatchIngestResponse(BaseModel):
    accepted: int
    rejected: int
    errors: list[BatchErrorResponse]

    @classmethod
    def from_result(cls, result: BatchIngestResult) -> "BatchIngestResponse":
        return cls(
            accepted=result.accepted,
            rejected=result.rejected,
            errors=[
                BatchErrorResponse(index=error.index, event_id=error.event_id, error=error.error)
                for error in result.errors
            ],
        )


class QueryEventsResponse(BaseModel):
    count: int
    events: list[EventResponse]

    @classmethod
    def from_events(cls, events: list[EventRecord]) -> "QueryEventsResponse":
        return cls(
            count=len(events),
            events=[EventResponse.from_domain(event) for event in events],
        )
