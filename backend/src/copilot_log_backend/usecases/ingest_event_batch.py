from __future__ import annotations

from dataclasses import dataclass, field

from copilot_log_backend.domain.entities.event import EventRecord
from copilot_log_backend.domain.exceptions import DomainError
from copilot_log_backend.domain.gateways.event_repository import EventRepository

from .ingest_event import IngestEventUseCase
from .ports import Sanitizer


@dataclass(slots=True)
class BatchIngestError:
    index: int
    event_id: str | None
    error: str


@dataclass(slots=True)
class BatchIngestResult:
    accepted: int
    rejected: int
    events: list[EventRecord] = field(default_factory=list)
    errors: list[BatchIngestError] = field(default_factory=list)


class IngestEventBatchUseCase:
    def __init__(
        self,
        repository: EventRepository,
        sanitizer: Sanitizer,
        *,
        allow_unknown_event_types: bool = False,
    ) -> None:
        self.repository = repository
        self.single_ingest = IngestEventUseCase(
            repository,
            sanitizer,
            allow_unknown_event_types=allow_unknown_event_types,
        )

    def execute(self, events: list[EventRecord]) -> BatchIngestResult:
        accepted_events: list[EventRecord] = []
        errors: list[BatchIngestError] = []

        for index, event in enumerate(events):
            try:
                self.single_ingest._validate(event)
                accepted_events.append(self.single_ingest._sanitize_event(event))
            except DomainError as exc:
                errors.append(BatchIngestError(index=index, event_id=event.event_id, error=str(exc)))

        saved = self.repository.save_many(accepted_events) if accepted_events else []
        return BatchIngestResult(
            accepted=len(saved),
            rejected=len(errors),
            events=saved,
            errors=errors,
        )
