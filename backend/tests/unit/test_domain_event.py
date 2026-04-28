from hashlib import sha256
from pathlib import Path

from copilot_log_backend.domain.entities.event import EventRecord


def test_event_record_is_domain_dataclass_without_framework_dependencies() -> None:
    event = EventRecord.new(
        event_id="event-1",
        session_id="session-1",
        event_type="userPromptSubmitted",
        timestamp=1704614460000,
        user_prompt="Explain this code",
    )

    assert event.timestamp.isoformat() == "2024-01-07T08:01:00+00:00"
    assert event.prompt_hash == sha256(b"Explain this code").hexdigest()


def test_domain_event_module_does_not_import_infrastructure() -> None:
    source = Path("backend/src/copilot_log_backend/domain/entities/event.py").read_text(encoding="utf-8")

    forbidden = ("fastapi", "sqlalchemy", "psycopg", "pydantic", "requests")
    assert not any(name in source.lower() for name in forbidden)
