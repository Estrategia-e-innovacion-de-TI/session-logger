import json

from copilot_session_logger.schema import EventRecord
from copilot_session_logger.storage_jsonl import JsonlEventWriter


def test_jsonl_writer_persists_event(tmp_path) -> None:
    writer = JsonlEventWriter(tmp_path)
    record = EventRecord(
        session_id="session-1",
        event_type="userPromptSubmitted",
        timestamp="2024-01-07T10:41:00+00:00",
        user_prompt="Explain this code",
    )

    output_path = writer.write(record)

    assert output_path.exists()
    contents = output_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(contents) == 1

    payload = json.loads(contents[0])
    assert payload["session_id"] == "session-1"
    assert payload["event_type"] == "userPromptSubmitted"
    assert payload["user_prompt"] == "Explain this code"

