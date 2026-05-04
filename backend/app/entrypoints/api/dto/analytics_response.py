from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.gateway.analytics_repository import (
    PromptImpact,
    RepositoryActivity,
    SessionSummary,
    ToolUsage,
)


class ToolUsageItem(BaseModel):
    tool_name: str
    event_count: int
    success_count: int
    failure_count: int
    average_duration_ms: float | None = None


class ToolUsageResponse(BaseModel):
    count: int
    items: list[ToolUsageItem]

    @classmethod
    def from_domain(cls, items: list[ToolUsage]) -> "ToolUsageResponse":
        return cls(count=len(items), items=[ToolUsageItem(**asdict(item)) for item in items])


class RepositoryActivityItem(BaseModel):
    repository: str
    event_count: int
    prompt_count: int
    tool_event_count: int
    files_touched_count: int


class RepositoryActivityResponse(BaseModel):
    count: int
    items: list[RepositoryActivityItem]

    @classmethod
    def from_domain(cls, items: list[RepositoryActivity]) -> "RepositoryActivityResponse":
        return cls(count=len(items), items=[RepositoryActivityItem(**asdict(item)) for item in items])


class PromptImpactItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_prompt_id: str = Field(serialization_alias="userPrompt_id")
    session_id: str | None
    repository: str | None
    prompt_text: str | None
    related_event_count: int
    files_touched_count: int
    commands_executed_count: int
    duration_ms: int | None = None


class PromptImpactResponse(BaseModel):
    count: int
    items: list[PromptImpactItem]

    @classmethod
    def from_domain(cls, items: list[PromptImpact]) -> "PromptImpactResponse":
        return cls(count=len(items), items=[PromptImpactItem(**asdict(item)) for item in items])


class SessionSummaryItem(BaseModel):
    session_id: str
    event_count: int
    prompt_count: int
    tool_event_count: int
    repositories: list[str]
    first_event_at: datetime | None = None
    last_event_at: datetime | None = None


class SessionSummaryResponse(BaseModel):
    count: int
    items: list[SessionSummaryItem]

    @classmethod
    def from_domain(cls, items: list[SessionSummary]) -> "SessionSummaryResponse":
        return cls(count=len(items), items=[SessionSummaryItem(**asdict(item)) for item in items])
