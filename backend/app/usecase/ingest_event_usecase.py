from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.exception.domain_exceptions import EventValidationError, UnsupportedEventTypeError
from app.domain.gateway.event_repository import EventRepository
from app.domain.gateway.sanitizer import Sanitizer
from app.domain.model.copilot_event import CopilotEvent, SUPPORTED_EVENT_TYPES


@dataclass(frozen=True, slots=True)
class IngestEventResult:
    event: CopilotEvent
    created: bool


class IngestEventUseCase:
    def __init__(
        self,
        event_repository: EventRepository,
        sanitizer: Sanitizer,
        *,
        allow_unknown_event_types: bool = False,
    ) -> None:
        self.event_repository = event_repository
        self.sanitizer = sanitizer
        self.allow_unknown_event_types = allow_unknown_event_types

    def execute(self, event: CopilotEvent) -> IngestEventResult:
        self._validate(event)
        existing = self.event_repository.find_by_event_id(event.event_id)
        if existing is not None:
            return IngestEventResult(event=existing, created=False)

        sanitized = self._sanitize_event(event)
        saved = self.event_repository.save(sanitized)
        return IngestEventResult(event=saved, created=True)

    def _validate(self, event: CopilotEvent) -> None:
        if not event.event_id:
            raise EventValidationError("event_id is required")
        if not event.session_id:
            raise EventValidationError("session_id is required")
        if not event.event_type:
            raise EventValidationError("event_type is required")
        if not self.allow_unknown_event_types and event.event_type not in SUPPORTED_EVENT_TYPES:
            raise UnsupportedEventTypeError(f"Unsupported event_type: {event.event_type}")

    def _sanitize_event(self, event: CopilotEvent) -> CopilotEvent:
        metadata = self.sanitizer.sanitize(event.metadata)
        if not isinstance(metadata, dict):
            metadata = {"value": metadata}
        commands = self.sanitizer.sanitize(event.commands_executed)
        if not isinstance(commands, list):
            commands = [str(commands)]
        return event.with_sanitized_values(
            prompt_text=_as_optional_str(self.sanitizer.sanitize(event.prompt_text)),
            assistant_response_summary=_as_optional_str(
                self.sanitizer.sanitize(event.assistant_response_summary)
            ),
            tool_input_summary=_as_optional_str(self.sanitizer.sanitize(event.tool_input_summary)),
            tool_result_summary=_as_optional_str(self.sanitizer.sanitize(event.tool_result_summary)),
            metadata=metadata,
            raw_payload=self.sanitizer.sanitize(event.raw_payload),
            commands_executed=[str(item) for item in commands],
        )


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

