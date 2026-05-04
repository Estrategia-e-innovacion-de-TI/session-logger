from __future__ import annotations

from typing import Protocol

from app.domain.model.copilot_event import CopilotEvent, EventFilters


class EventRepository(Protocol):
    def save(self, event: CopilotEvent) -> CopilotEvent:
        ...

    def save_batch(self, events: list[CopilotEvent]) -> list[CopilotEvent]:
        ...

    def find_by_event_id(self, event_id: str) -> CopilotEvent | None:
        ...

    def find_by_session_id(self, session_id: str) -> list[CopilotEvent]:
        ...

    def find_by_user_prompt_id(self, user_prompt_id: str) -> list[CopilotEvent]:
        ...

    def find_by_parent_userPrompt_id(self, parent_userPrompt_id: str) -> list[CopilotEvent]:
        ...

    def find_events(self, filters: EventFilters) -> list[CopilotEvent]:
        ...

    def health(self) -> bool:
        return True

