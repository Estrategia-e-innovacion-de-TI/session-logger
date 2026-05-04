from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AnalyticsFilters:
    session_id: str | None = None
    repository: str | None = None
    user_id: str | None = None
    tool_name: str | None = None
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class ToolUsage:
    tool_name: str
    event_count: int
    success_count: int
    failure_count: int
    average_duration_ms: float | None = None


@dataclass(frozen=True, slots=True)
class RepositoryActivity:
    repository: str
    event_count: int
    prompt_count: int
    tool_event_count: int
    files_touched_count: int


@dataclass(frozen=True, slots=True)
class PromptImpact:
    user_prompt_id: str
    session_id: str | None
    repository: str | None
    prompt_text: str | None
    related_event_count: int
    files_touched_count: int
    commands_executed_count: int
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SessionSummary:
    session_id: str
    event_count: int
    prompt_count: int
    tool_event_count: int
    repositories: list[str] = field(default_factory=list)
    first_event_at: datetime | None = None
    last_event_at: datetime | None = None


class AnalyticsRepository(Protocol):
    def get_tool_usage(self, filters: AnalyticsFilters) -> list[ToolUsage]:
        ...

    def get_repository_activity(self, filters: AnalyticsFilters) -> list[RepositoryActivity]:
        ...

    def get_prompt_impact(self, filters: AnalyticsFilters) -> list[PromptImpact]:
        ...

    def get_session_summary(self, filters: AnalyticsFilters) -> list[SessionSummary]:
        ...

