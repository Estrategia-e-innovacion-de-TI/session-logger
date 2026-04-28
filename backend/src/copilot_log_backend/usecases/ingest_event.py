from __future__ import annotations

from typing import Any

from copilot_log_backend.domain.entities.event import EventRecord, SUPPORTED_EVENT_TYPES
from copilot_log_backend.domain.exceptions import EventValidationError, UnsupportedEventTypeError
from copilot_log_backend.domain.gateways.event_repository import EventRepository

from .ports import Sanitizer


class IngestEventUseCase:
    def __init__(
        self,
        repository: EventRepository,
        sanitizer: Sanitizer,
        *,
        allow_unknown_event_types: bool = False,
    ) -> None:
        self.repository = repository
        self.sanitizer = sanitizer
        self.allow_unknown_event_types = allow_unknown_event_types

    def execute(self, event: EventRecord) -> EventRecord:
        self._validate(event)
        sanitized = self._sanitize_event(event)
        return self.repository.save(sanitized)

    def _validate(self, event: EventRecord) -> None:
        if not event.session_id:
            raise EventValidationError("session_id is required")
        if not event.event_type:
            raise EventValidationError("event_type is required")
        if self.allow_unknown_event_types:
            return
        if event.event_type not in SUPPORTED_EVENT_TYPES:
            raise UnsupportedEventTypeError(f"Unsupported event_type: {event.event_type}")

    def _sanitize_event(self, event: EventRecord) -> EventRecord:
        metadata = self.sanitizer.sanitize(event.metadata)
        if not isinstance(metadata, dict):
            metadata = {"value": metadata}
        return event.with_sanitized_values(
            user_prompt=_as_optional_str(self.sanitizer.sanitize(event.user_prompt)),
            raw_payload=self.sanitizer.sanitize(event.raw_payload),
            metadata=metadata,
            command=_as_optional_str(self.sanitizer.sanitize(event.command)),
            error=_as_optional_str(self.sanitizer.sanitize(event.error)),
        )


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
