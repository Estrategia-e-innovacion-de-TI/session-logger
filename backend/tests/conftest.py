from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import BackendSettings
from app.domain.gateway.analytics_repository import (
    AnalyticsFilters,
    PromptImpact,
    RepositoryActivity,
    SessionSummary,
    ToolUsage,
)
from app.domain.model.copilot_event import CopilotEvent, EventFilters
from app.driven_adapters.observability.metrics import InMemoryMetrics
from app.driven_adapters.security.api_key_validator import ApiKeyValidator
from app.driven_adapters.security.sanitizer import RegexSanitizer
from app.usecase.get_prompt_impact_usecase import GetPromptImpactUseCase
from app.usecase.get_prompt_trace_usecase import GetPromptTraceUseCase
from app.usecase.get_repository_activity_usecase import GetRepositoryActivityUseCase
from app.usecase.get_session_summary_usecase import GetSessionSummaryUseCase
from app.usecase.get_session_trace_usecase import GetSessionTraceUseCase
from app.usecase.get_tool_usage_analytics_usecase import GetToolUsageAnalyticsUseCase
from app.usecase.health_check_usecase import HealthCheckUseCase
from app.usecase.ingest_batch_events_usecase import IngestBatchEventsUseCase
from app.usecase.ingest_event_usecase import IngestEventUseCase
from app.usecase.query_events_usecase import QueryEventsUseCase


class InMemoryEventRepository:
    def __init__(self) -> None:
        self.events: dict[str, CopilotEvent] = {}

    def save(self, event: CopilotEvent) -> CopilotEvent:
        if event.event_id in self.events:
            return self.events[event.event_id]
        self.events[event.event_id] = event
        return event

    def save_batch(self, events: list[CopilotEvent]) -> list[CopilotEvent]:
        return [self.save(event) for event in events]

    def find_by_event_id(self, event_id: str) -> CopilotEvent | None:
        return self.events.get(event_id)

    def find_by_session_id(self, session_id: str) -> list[CopilotEvent]:
        return sorted(
            [event for event in self.events.values() if event.session_id == session_id],
            key=lambda event: event.timestamp,
        )

    def find_by_user_prompt_id(self, user_prompt_id: str) -> list[CopilotEvent]:
        return sorted(
            [event for event in self.events.values() if event.user_prompt_id == user_prompt_id],
            key=lambda event: event.timestamp,
        )

    def find_by_parent_userPrompt_id(self, parent_userPrompt_id: str) -> list[CopilotEvent]:
        return sorted(
            [
                event
                for event in self.events.values()
                if event.parent_user_prompt_id == parent_userPrompt_id
            ],
            key=lambda event: event.timestamp,
        )

    def find_events(self, filters: EventFilters) -> list[CopilotEvent]:
        events = list(self.events.values())
        if filters.session_id:
            events = [event for event in events if event.session_id == filters.session_id]
        if filters.event_type:
            events = [event for event in events if event.event_type == filters.event_type]
        if filters.repository:
            events = [event for event in events if event.repository == filters.repository]
        if filters.user_id:
            events = [event for event in events if event.user_id == filters.user_id]
        if filters.user_prompt_id:
            events = [event for event in events if event.user_prompt_id == filters.user_prompt_id]
        if filters.parent_user_prompt_id:
            events = [
                event for event in events if event.parent_user_prompt_id == filters.parent_user_prompt_id
            ]
        if filters.tool_name:
            events = [event for event in events if event.tool_name == filters.tool_name]
        if filters.from_timestamp:
            events = [event for event in events if event.timestamp >= filters.from_timestamp]
        if filters.to_timestamp:
            events = [event for event in events if event.timestamp <= filters.to_timestamp]
        return sorted(events, key=lambda event: event.timestamp, reverse=True)[: filters.limit]

    def health(self) -> bool:
        return True


class InMemoryAnalyticsRepository:
    def __init__(self, repository: InMemoryEventRepository) -> None:
        self.repository = repository

    def get_tool_usage(self, filters: AnalyticsFilters) -> list[ToolUsage]:
        events = [event for event in self._events(filters) if event.tool_name]
        return [
            ToolUsage(
                tool_name=tool_name,
                event_count=len(group),
                success_count=sum(1 for event in group if event.status == "success"),
                failure_count=sum(1 for event in group if event.status == "failed"),
            )
            for tool_name, group in _group_by(events, lambda event: event.tool_name or "unknown").items()
        ]

    def get_repository_activity(self, filters: AnalyticsFilters) -> list[RepositoryActivity]:
        events = [event for event in self._events(filters) if event.repository]
        return [
            RepositoryActivity(
                repository=repository,
                event_count=len(group),
                prompt_count=sum(1 for event in group if event.event_type in {"userPromptSubmitted", "user_prompt"}),
                tool_event_count=sum(1 for event in group if event.tool_name),
                files_touched_count=len({file for event in group for file in event.files_touched}),
            )
            for repository, group in _group_by(events, lambda event: event.repository or "unknown").items()
        ]

    def get_prompt_impact(self, filters: AnalyticsFilters) -> list[PromptImpact]:
        events = self._events(filters)
        groups = _group_by(events, lambda event: event.parent_user_prompt_id or event.user_prompt_id or "")
        return [
            PromptImpact(
                user_prompt_id=prompt_id,
                session_id=group[0].session_id,
                repository=group[0].repository,
                prompt_text=next((event.prompt_text for event in group if event.prompt_text), None),
                related_event_count=len(group),
                files_touched_count=len({file for event in group for file in event.files_touched}),
                commands_executed_count=len(
                    {command for event in group for command in event.commands_executed}
                ),
            )
            for prompt_id, group in groups.items()
            if prompt_id
        ]

    def get_session_summary(self, filters: AnalyticsFilters) -> list[SessionSummary]:
        events = self._events(filters)
        return [
            SessionSummary(
                session_id=session_id,
                event_count=len(group),
                prompt_count=sum(1 for event in group if event.event_type in {"userPromptSubmitted", "user_prompt"}),
                tool_event_count=sum(1 for event in group if event.tool_name),
                repositories=sorted({event.repository for event in group if event.repository}),
                first_event_at=min(event.timestamp for event in group),
                last_event_at=max(event.timestamp for event in group),
            )
            for session_id, group in _group_by(events, lambda event: event.session_id).items()
        ]

    def _events(self, filters: AnalyticsFilters) -> list[CopilotEvent]:
        event_filters = EventFilters(
            session_id=filters.session_id,
            repository=filters.repository,
            user_id=filters.user_id,
            tool_name=filters.tool_name,
            from_timestamp=filters.from_timestamp,
            to_timestamp=filters.to_timestamp,
            limit=filters.limit,
        )
        return self.repository.find_events(event_filters)


class AppTestContainer:
    def __init__(self, settings: BackendSettings) -> None:
        self.settings = settings
        self.event_repository = InMemoryEventRepository()
        self.analytics_repository = InMemoryAnalyticsRepository(self.event_repository)
        self.sanitizer = RegexSanitizer()
        self.api_key_validator = ApiKeyValidator(settings.api_keys)
        self.metrics = InMemoryMetrics()

    def ingest_event_use_case(self) -> IngestEventUseCase:
        return IngestEventUseCase(
            self.event_repository,
            self.sanitizer,
            allow_unknown_event_types=self.settings.allow_unknown_event_types,
        )

    def ingest_batch_events_use_case(self) -> IngestBatchEventsUseCase:
        return IngestBatchEventsUseCase(
            self.event_repository,
            self.sanitizer,
            allow_unknown_event_types=self.settings.allow_unknown_event_types,
        )

    def query_events_use_case(self) -> QueryEventsUseCase:
        return QueryEventsUseCase(self.event_repository, max_limit=self.settings.query_limit)

    def get_session_trace_use_case(self) -> GetSessionTraceUseCase:
        return GetSessionTraceUseCase(self.event_repository)

    def get_prompt_trace_use_case(self) -> GetPromptTraceUseCase:
        return GetPromptTraceUseCase(self.event_repository)

    def get_tool_usage_analytics_use_case(self) -> GetToolUsageAnalyticsUseCase:
        return GetToolUsageAnalyticsUseCase(self.analytics_repository)

    def get_repository_activity_use_case(self) -> GetRepositoryActivityUseCase:
        return GetRepositoryActivityUseCase(self.analytics_repository)

    def get_prompt_impact_use_case(self) -> GetPromptImpactUseCase:
        return GetPromptImpactUseCase(self.analytics_repository)

    def get_session_summary_use_case(self) -> GetSessionSummaryUseCase:
        return GetSessionSummaryUseCase(self.analytics_repository)

    def health_check_use_case(self) -> HealthCheckUseCase:
        return HealthCheckUseCase(self.event_repository, storage="postgres")


def _group_by(events, key_factory):
    groups = {}
    for event in events:
        key = key_factory(event)
        groups.setdefault(key, []).append(event)
    return groups


@pytest.fixture()
def sample_event_dict():
    return {
        "event_id": "event-1",
        "session_id": "session-1",
        "event_type": "userPromptSubmitted",
        "timestamp": 1704614500000,
        "userPrompt_id": "prompt-1",
        "prompt_text": "Explain this code",
        "repository": "demo-repo",
        "user_id": "alice",
        "raw_payload": {"prompt": "Explain this code"},
        "metadata": {"source": "test"},
    }
