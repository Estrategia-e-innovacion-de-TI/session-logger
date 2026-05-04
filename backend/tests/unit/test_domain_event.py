from hashlib import sha256
from pathlib import Path

from app.domain.model.copilot_event import CopilotEvent

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_copilot_event_is_domain_dataclass_without_framework_dependencies() -> None:
    event = CopilotEvent.new(
        event_id="event-1",
        session_id="session-1",
        event_type="userPromptSubmitted",
        timestamp=1704614460000,
        prompt_text="Explain this code",
    )

    assert event.timestamp.isoformat() == "2024-01-07T08:01:00+00:00"
    assert event.prompt_hash == sha256(b"Explain this code").hexdigest()


def test_domain_model_does_not_import_infrastructure_or_frameworks() -> None:
    domain_dir = BACKEND_ROOT / "app/domain"
    source = "\n".join(path.read_text(encoding="utf-8") for path in domain_dir.rglob("*.py"))

    forbidden = ("fastapi", "sqlalchemy", "psycopg", "pydantic", "requests", "postgres")
    assert not any(name in source.lower() for name in forbidden)
