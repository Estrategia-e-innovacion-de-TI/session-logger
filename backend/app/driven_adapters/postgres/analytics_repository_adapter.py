from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.gateway.analytics_repository import (
    AnalyticsFilters,
    PromptImpact,
    RepositoryActivity,
    SessionSummary,
    ToolUsage,
)
from app.domain.model.copilot_event import CopilotEvent, EventFilters

from .event_repository_adapter import _apply_filters, _to_domain
from .models import CopilotEventModel

PROMPT_EVENT_TYPES = {"userPromptSubmitted", "user_prompt"}


class PostgresAnalyticsRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def get_tool_usage(self, filters: AnalyticsFilters) -> list[ToolUsage]:
        events = [event for event in self._events(filters) if event.tool_name]
        grouped: dict[str, list[CopilotEvent]] = defaultdict(list)
        for event in events:
            grouped[event.tool_name or "unknown"].append(event)

        result = []
        for tool_name, tool_events in grouped.items():
            durations = [event.duration_ms for event in tool_events if event.duration_ms is not None]
            result.append(
                ToolUsage(
                    tool_name=tool_name,
                    event_count=len(tool_events),
                    success_count=sum(1 for event in tool_events if _is_success(event.status)),
                    failure_count=sum(1 for event in tool_events if _is_failure(event.status)),
                    average_duration_ms=(sum(durations) / len(durations)) if durations else None,
                )
            )
        return sorted(result, key=lambda item: item.event_count, reverse=True)

    def get_repository_activity(self, filters: AnalyticsFilters) -> list[RepositoryActivity]:
        events = [event for event in self._events(filters) if event.repository]
        grouped: dict[str, list[CopilotEvent]] = defaultdict(list)
        for event in events:
            grouped[event.repository or "unknown"].append(event)

        result = []
        for repository, repo_events in grouped.items():
            files = {file for event in repo_events for file in event.files_touched}
            result.append(
                RepositoryActivity(
                    repository=repository,
                    event_count=len(repo_events),
                    prompt_count=sum(1 for event in repo_events if event.event_type in PROMPT_EVENT_TYPES),
                    tool_event_count=sum(1 for event in repo_events if event.tool_name),
                    files_touched_count=len(files),
                )
            )
        return sorted(result, key=lambda item: item.event_count, reverse=True)

    def get_prompt_impact(self, filters: AnalyticsFilters) -> list[PromptImpact]:
        events = self._events(filters)
        grouped: dict[str, list[CopilotEvent]] = defaultdict(list)
        for event in events:
            prompt_id = event.parent_user_prompt_id or event.user_prompt_id
            if prompt_id:
                grouped[prompt_id].append(event)

        result = []
        for prompt_id, prompt_events in grouped.items():
            root = next((event for event in prompt_events if event.user_prompt_id == prompt_id), None)
            files = {file for event in prompt_events for file in event.files_touched}
            commands = {command for event in prompt_events for command in event.commands_executed}
            durations = [event.duration_ms for event in prompt_events if event.duration_ms is not None]
            result.append(
                PromptImpact(
                    user_prompt_id=prompt_id,
                    session_id=root.session_id if root else prompt_events[0].session_id,
                    repository=root.repository if root else prompt_events[0].repository,
                    prompt_text=root.prompt_text if root else None,
                    related_event_count=len(prompt_events),
                    files_touched_count=len(files),
                    commands_executed_count=len(commands),
                    duration_ms=sum(durations) if durations else None,
                )
            )
        return sorted(result, key=lambda item: item.related_event_count, reverse=True)

    def get_session_summary(self, filters: AnalyticsFilters) -> list[SessionSummary]:
        grouped: dict[str, list[CopilotEvent]] = defaultdict(list)
        for event in self._events(filters):
            grouped[event.session_id].append(event)

        result = []
        for session_id, session_events in grouped.items():
            ordered = sorted(session_events, key=lambda event: event.timestamp)
            repositories = sorted({event.repository for event in ordered if event.repository})
            result.append(
                SessionSummary(
                    session_id=session_id,
                    event_count=len(ordered),
                    prompt_count=sum(1 for event in ordered if event.event_type in PROMPT_EVENT_TYPES),
                    tool_event_count=sum(1 for event in ordered if event.tool_name),
                    repositories=repositories,
                    first_event_at=ordered[0].timestamp if ordered else None,
                    last_event_at=ordered[-1].timestamp if ordered else None,
                )
            )
        return sorted(result, key=lambda item: item.event_count, reverse=True)

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
        query = _apply_filters(select(CopilotEventModel), event_filters)
        query = query.order_by(CopilotEventModel.timestamp.asc()).limit(max(filters.limit, 1))
        with self.session_factory() as session:
            return [_to_domain(model) for model in session.scalars(query).all()]


def _is_success(status: str | None) -> bool:
    return (status or "").lower() in {"success", "succeeded", "ok", "completed", "accepted"}


def _is_failure(status: str | None) -> bool:
    return (status or "").lower() in {"error", "failed", "failure", "rejected"}
