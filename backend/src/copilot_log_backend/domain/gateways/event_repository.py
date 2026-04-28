from __future__ import annotations

from typing import Protocol

from ..entities.event import EventRecord


class EventRepository(Protocol):
    def save(self, event: EventRecord) -> EventRecord:
        ...

    def save_many(self, events: list[EventRecord]) -> list[EventRecord]:
        ...

    def find(
        self,
        *,
        session_id: str | None,
        event_type: str | None,
        repo_name: str | None,
        actor: str | None,
        from_timestamp: str | None,
        to_timestamp: str | None,
        limit: int,
    ) -> list[EventRecord]:
        ...

    def health(self) -> bool:
        return True
