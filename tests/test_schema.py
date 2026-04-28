from hashlib import sha256

import pytest

from copilot_session_logger.schema import EventRecord


def test_event_record_computes_prompt_hash() -> None:
    record = EventRecord(
        session_id="session-1",
        event_type="userPromptSubmitted",
        timestamp=1704614460000,
        user_prompt="Explain this code",
    )

    assert record.prompt_hash == sha256(b"Explain this code").hexdigest()
    assert record.timestamp.isoformat() == "2024-01-07T08:01:00+00:00"


def test_event_record_rejects_invalid_event_type() -> None:
    with pytest.raises(ValueError):
        EventRecord(session_id="session-1", event_type="invalid-event")
