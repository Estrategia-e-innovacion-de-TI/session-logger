from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .copilot_event import CopilotEvent


@dataclass(frozen=True, slots=True)
class Session:
    session_id: str
    events: list[CopilotEvent] = field(default_factory=list)

    @classmethod
    def from_events(cls, session_id: str, events: list[CopilotEvent]) -> "Session":
        ordered = sorted(events, key=lambda event: event.timestamp)
        return cls(session_id=session_id, events=ordered)

    @property
    def first_event_at(self) -> datetime | None:
        return self.events[0].timestamp if self.events else None

    @property
    def last_event_at(self) -> datetime | None:
        return self.events[-1].timestamp if self.events else None

    @property
    def repositories(self) -> list[str]:
        return sorted({event.repository for event in self.events if event.repository})

