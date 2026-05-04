from __future__ import annotations

from app.domain.gateway.event_repository import EventRepository
from app.domain.model.copilot_event import CopilotEvent
from app.domain.model.user_prompt import UserPrompt


class GetPromptTraceUseCase:
    def __init__(self, event_repository: EventRepository) -> None:
        self.event_repository = event_repository

    def execute(self, user_prompt_id: str) -> UserPrompt:
        root_events = self.event_repository.find_by_user_prompt_id(user_prompt_id)
        child_events = self.event_repository.find_by_parent_userPrompt_id(user_prompt_id)
        return UserPrompt.from_events(user_prompt_id, _dedupe_and_sort([*root_events, *child_events]))


def _dedupe_and_sort(events: list[CopilotEvent]) -> list[CopilotEvent]:
    by_id = {event.event_id: event for event in events}
    return sorted(by_id.values(), key=lambda event: event.timestamp)

