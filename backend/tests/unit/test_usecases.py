from __future__ import annotations

import pytest

from copilot_log_backend.domain.entities.event import EventRecord
from copilot_log_backend.domain.exceptions import UnsupportedEventTypeError
from copilot_log_backend.driven_adapters.security.sanitizer import RegexSanitizer
from copilot_log_backend.usecases.ingest_event import IngestEventUseCase
from copilot_log_backend.usecases.ingest_event_batch import IngestEventBatchUseCase
from copilot_log_backend.usecases.query_events import QueryEventsUseCase


class FakeEventRepository:
    def __init__(self) -> None:
        self.events = []

    def save(self, event):
        self.events.append(event)
        return event

    def save_many(self, events):
        self.events.extend(events)
        return events

    def find(self, **filters):
        limit = filters["limit"]
        events = self.events
        if filters.get("event_type"):
            events = [event for event in events if event.event_type == filters["event_type"]]
        return events[:limit]

    def health(self):
        return True


def _event(**overrides):
    data = {
        "event_id": "event-1",
        "session_id": "session-1",
        "event_type": "userPromptSubmitted",
        "timestamp": 1704614460000,
        "user_prompt": "Use sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        "command": "echo password=secret",
        "raw_payload": {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def"},
        "metadata": {"api_key": "plain-secret"},
    }
    data.update(overrides)
    return EventRecord(**data)


def test_ingest_event_sanitizes_before_persisting() -> None:
    repository = FakeEventRepository()
    usecase = IngestEventUseCase(repository, RegexSanitizer())

    saved = usecase.execute(_event())

    assert saved.user_prompt == "Use [REDACTED:OPENAI_KEY]"
    assert saved.command == "echo password=[REDACTED]"
    assert saved.raw_payload["Authorization"] == "[REDACTED]"
    assert saved.metadata["api_key"] == "[REDACTED]"
    assert repository.events[0] is saved


def test_ingest_event_rejects_unknown_event_type() -> None:
    usecase = IngestEventUseCase(FakeEventRepository(), RegexSanitizer())

    with pytest.raises(UnsupportedEventTypeError):
        usecase.execute(_event(event_type="unknownEvent"))


def test_batch_ingest_accepts_valid_and_rejects_unknown() -> None:
    repository = FakeEventRepository()
    usecase = IngestEventBatchUseCase(repository, RegexSanitizer())

    result = usecase.execute([
        _event(event_id="event-1"),
        _event(event_id="event-2", event_type="unknownEvent"),
    ])

    assert result.accepted == 1
    assert result.rejected == 1
    assert result.errors[0].index == 1
    assert len(repository.events) == 1


def test_query_usecase_caps_limit() -> None:
    repository = FakeEventRepository()
    repository.save_many([_event(event_id=f"event-{index}") for index in range(5)])
    usecase = QueryEventsUseCase(repository, max_limit=2)

    result = usecase.execute(limit=10)

    assert len(result) == 2
