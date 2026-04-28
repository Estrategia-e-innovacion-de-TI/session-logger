from __future__ import annotations

from copilot_log_backend.domain.entities.event import EventRecord
from copilot_log_backend.domain.gateways.event_repository import EventRepository


class QueryEventsUseCase:
    def __init__(self, repository: EventRepository, *, max_limit: int = 100) -> None:
        self.repository = repository
        self.max_limit = max_limit

    def execute(
        self,
        *,
        session_id: str | None = None,
        event_type: str | None = None,
        repo_name: str | None = None,
        actor: str | None = None,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
        limit: int | None = None,
    ) -> list[EventRecord]:
        effective_limit = min(max(limit or self.max_limit, 1), self.max_limit)
        return self.repository.find(
            session_id=session_id,
            event_type=event_type,
            repo_name=repo_name,
            actor=actor,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            limit=effective_limit,
        )
