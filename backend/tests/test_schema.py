from hashlib import sha256

import pytest

from copilot_log_backend.schema import EventRecord, validate_event_type_allowed


def test_event_record_normalizes_timestamp_and_prompt_hash() -> None:
    record = EventRecord(
        session_id="session-1",
        event_type="userPromptSubmitted",
        timestamp=1704614460000,
        user_prompt="Explain this code",
    )

    assert record.timestamp.isoformat() == "2024-01-07T08:01:00+00:00"
    assert record.prompt_hash == sha256(b"Explain this code").hexdigest()


def test_validate_event_type_rejects_unknown_by_default() -> None:
    with pytest.raises(ValueError):
        validate_event_type_allowed("unknownEvent", allow_unknown=False)


def test_validate_event_type_allows_unknown_when_configured() -> None:
    validate_event_type_allowed("unknownEvent", allow_unknown=True)
