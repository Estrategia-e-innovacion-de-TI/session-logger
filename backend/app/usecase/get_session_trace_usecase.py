from __future__ import annotations

from app.domain.gateway.event_repository import EventRepository
from app.domain.model.session import Session


class GetSessionTraceUseCase:
    def __init__(self, event_repository: EventRepository) -> None:
        self.event_repository = event_repository

    def execute(self, session_id: str) -> Session:
        events = self.event_repository.find_by_session_id(session_id)
        return Session.from_events(session_id, events)

