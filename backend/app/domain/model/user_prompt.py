from __future__ import annotations

from dataclasses import dataclass, field

from .copilot_event import CopilotEvent


@dataclass(frozen=True, slots=True)
class UserPrompt:
    user_prompt_id: str
    session_id: str | None = None
    prompt_text: str | None = None
    parent_user_prompt_id: str | None = None
    events: list[CopilotEvent] = field(default_factory=list)

    @classmethod
    def from_events(cls, user_prompt_id: str, events: list[CopilotEvent]) -> "UserPrompt":
        ordered = sorted(events, key=lambda event: event.timestamp)
        root = next((event for event in ordered if event.user_prompt_id == user_prompt_id), None)
        return cls(
            user_prompt_id=user_prompt_id,
            session_id=root.session_id if root else (ordered[0].session_id if ordered else None),
            prompt_text=root.prompt_text if root else None,
            parent_user_prompt_id=root.parent_user_prompt_id if root else None,
            events=ordered,
        )

