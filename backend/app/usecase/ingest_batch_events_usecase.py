from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.exception.domain_exceptions import DomainError
from app.domain.gateway.event_repository import EventRepository
from app.domain.gateway.sanitizer import Sanitizer
from app.domain.model.copilot_event import CopilotEvent

from .ingest_event_usecase import IngestEventUseCase


@dataclass(frozen=True, slots=True)
class BatchIngestError:
    index: int
    event_id: str | None
    error: str


@dataclass(frozen=True, slots=True)
class BatchIngestResult:
    accepted: int
    rejected: int
    created: int
    duplicated: int
    events: list[CopilotEvent] = field(default_factory=list)
    errors: list[BatchIngestError] = field(default_factory=list)


class IngestBatchEventsUseCase:
    def __init__(
        self,
        event_repository: EventRepository,
        sanitizer: Sanitizer,
        *,
        allow_unknown_event_types: bool = False,
    ) -> None:
        self.event_repository = event_repository
        self.single_ingest = IngestEventUseCase(
            event_repository,
            sanitizer,
            allow_unknown_event_types=allow_unknown_event_types,
        )

    def execute(self, events: list[CopilotEvent]) -> BatchIngestResult:
        to_save_by_id: dict[str, CopilotEvent] = {}
        duplicate_pending_ids: list[str] = []
        accepted_existing: list[CopilotEvent] = []
        errors: list[BatchIngestError] = []

        for index, event in enumerate(events):
            try:
                self.single_ingest._validate(event)
                if event.event_id in to_save_by_id:
                    duplicate_pending_ids.append(event.event_id)
                    continue
                existing = self.event_repository.find_by_event_id(event.event_id)
                if existing is not None:
                    accepted_existing.append(existing)
                    continue
                to_save_by_id[event.event_id] = self.single_ingest._sanitize_event(event)
            except DomainError as exc:
                errors.append(BatchIngestError(index=index, event_id=event.event_id, error=str(exc)))

        to_save = list(to_save_by_id.values())
        saved = self.event_repository.save_batch(to_save) if to_save else []
        saved_by_id = {event.event_id: event for event in saved}
        accepted_pending_duplicates = [
            saved_by_id[event_id] for event_id in duplicate_pending_ids if event_id in saved_by_id
        ]
        accepted_events = [*accepted_existing, *saved, *accepted_pending_duplicates]
        return BatchIngestResult(
            accepted=len(accepted_events),
            rejected=len(errors),
            created=len(saved),
            duplicated=len(accepted_existing) + len(accepted_pending_duplicates),
            events=accepted_events,
            errors=errors,
        )
