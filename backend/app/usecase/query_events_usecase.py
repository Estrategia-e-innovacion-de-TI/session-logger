from __future__ import annotations

from app.domain.gateway.event_repository import EventRepository
from app.domain.model.copilot_event import CopilotEvent, EventFilters


class QueryEventsUseCase:
    def __init__(self, event_repository: EventRepository, *, max_limit: int = 100) -> None:
        self.event_repository = event_repository
        self.max_limit = max_limit

    def execute(self, filters: EventFilters) -> list[CopilotEvent]:
        return self.event_repository.find_events(filters.normalized(max_limit=self.max_limit))

