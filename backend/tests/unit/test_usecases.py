from __future__ import annotations

import pytest

from app.domain.exception.domain_exceptions import UnsupportedEventTypeError
from app.domain.model.copilot_event import CopilotEvent, EventFilters
from app.driven_adapters.security.sanitizer import RegexSanitizer
from app.usecase.get_prompt_trace_usecase import GetPromptTraceUseCase
from app.usecase.get_session_trace_usecase import GetSessionTraceUseCase
from app.usecase.ingest_batch_events_usecase import IngestBatchEventsUseCase
from app.usecase.ingest_event_usecase import IngestEventUseCase
from app.usecase.query_events_usecase import QueryEventsUseCase

from conftest import InMemoryEventRepository


def _event(**overrides):
    data = {
        "event_id": "event-1",
        "session_id": "session-1",
        "event_type": "userPromptSubmitted",
        "timestamp": 1704614460000,
        "user_prompt_id": "prompt-1",
        "prompt_text": "Use sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        "commands_executed": ["echo password=secret"],
        "raw_payload": {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def"},
        "metadata": {"api_key": "plain-secret"},
    }
    data.update(overrides)
    return CopilotEvent(**data)


def test_ingest_event_sanitizes_before_persisting() -> None:
    repository = InMemoryEventRepository()
    usecase = IngestEventUseCase(repository, RegexSanitizer())

    result = usecase.execute(_event())

    assert result.created is True
    assert result.event.prompt_text == "Use [REDACTED:OPENAI_KEY]"
    assert result.event.commands_executed == ["echo password=[REDACTED]"]
    assert result.event.raw_payload["Authorization"] == "[REDACTED]"
    assert result.event.metadata["api_key"] == "[REDACTED]"


def test_ingest_event_is_idempotent_by_event_id() -> None:
    repository = InMemoryEventRepository()
    usecase = IngestEventUseCase(repository, RegexSanitizer())

    first = usecase.execute(_event(prompt_text="first"))
    second = usecase.execute(_event(prompt_text="second"))

    assert first.created is True
    assert second.created is False
    assert len(repository.events) == 1
    assert second.event.prompt_text == "first"


def test_ingest_event_rejects_unknown_event_type() -> None:
    usecase = IngestEventUseCase(InMemoryEventRepository(), RegexSanitizer())

    with pytest.raises(UnsupportedEventTypeError):
        usecase.execute(_event(event_type="unknownEvent"))


def test_batch_ingest_accepts_valid_rejects_unknown_and_counts_duplicates() -> None:
    repository = InMemoryEventRepository()
    usecase = IngestBatchEventsUseCase(repository, RegexSanitizer())

    result = usecase.execute(
        [
            _event(event_id="event-1"),
            _event(event_id="event-1", prompt_text="duplicate"),
            _event(event_id="event-2", event_type="unknownEvent"),
        ]
    )

    assert result.accepted == 2
    assert result.created == 1
    assert result.duplicated == 1
    assert result.rejected == 1
    assert len(repository.events) == 1


def test_query_usecase_caps_limit() -> None:
    repository = InMemoryEventRepository()
    repository.save_batch([_event(event_id=f"event-{index}") for index in range(5)])
    usecase = QueryEventsUseCase(repository, max_limit=2)

    result = usecase.execute(EventFilters(limit=10))

    assert len(result) == 2


def test_session_trace_returns_ordered_domain_session() -> None:
    repository = InMemoryEventRepository()
    repository.save_batch(
        [
            _event(event_id="event-2", timestamp=1704614520000),
            _event(event_id="event-1", timestamp=1704614460000),
        ]
    )

    session = GetSessionTraceUseCase(repository).execute("session-1")

    assert [event.event_id for event in session.events] == ["event-1", "event-2"]


def test_prompt_trace_uses_user_prompt_and_parent_user_prompt_ids() -> None:
    repository = InMemoryEventRepository()
    repository.save_batch(
        [
            _event(event_id="prompt-root", user_prompt_id="prompt-1"),
            _event(
                event_id="tool-child",
                event_type="preToolUse",
                user_prompt_id=None,
                parent_user_prompt_id="prompt-1",
                tool_name="bash",
            ),
        ]
    )

    trace = GetPromptTraceUseCase(repository).execute("prompt-1")

    assert trace.user_prompt_id == "prompt-1"
    assert [event.event_id for event in trace.events] == ["prompt-root", "tool-child"]
