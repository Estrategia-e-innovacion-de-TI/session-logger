import json

from copilot_session_logger.offline_queue import OfflineQueue
from copilot_session_logger.schema import EventRecord
from copilot_session_logger.storage_http import HttpSendResult


class _Sender:
    def __init__(self, *results):
        self.results = list(results)
        self.events = []

    def send_event(self, event):
        self.events.append(event)
        return self.results.pop(0)


def _jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_offline_queue_sends_pending_event(tmp_path) -> None:
    queue = OfflineQueue(tmp_path, max_retries=3)
    record = EventRecord(
        session_id="session-1",
        event_type="userPromptSubmitted",
        raw_payload={"password": "super-secret"},
    )
    queue.enqueue(record, retry_count=1, last_error="http_500")

    summary = queue.process_pending(_Sender(HttpSendResult(success=True, retryable=False, status_code=202)))

    assert summary.sent == 1
    assert summary.remaining == 0
    assert _jsonl(queue.pending_path) == []
    sent = _jsonl(queue.sent_path)
    assert sent[0]["event_id"] == record.event_id
    assert sent[0]["event"]["raw_payload"]["password"] == "[REDACTED]"


def test_offline_queue_moves_exhausted_retry_to_dead_letter(tmp_path) -> None:
    queue = OfflineQueue(tmp_path, max_retries=2)
    record = EventRecord(session_id="session-1", event_type="sessionStart")
    queue.enqueue(record, retry_count=1, last_error="http_500")

    summary = queue.process_pending(
        _Sender(HttpSendResult(success=False, retryable=True, status_code=500, error="http_500"))
    )

    assert summary.dead_lettered == 1
    assert summary.remaining == 0
    assert _jsonl(queue.pending_path) == []
    dead = _jsonl(queue.dead_letter_path)
    assert dead[0]["event_id"] == record.event_id
    assert dead[0]["retry_count"] == 2


def test_offline_queue_keeps_retryable_event_pending(tmp_path) -> None:
    queue = OfflineQueue(tmp_path, max_retries=3)
    record = EventRecord(session_id="session-1", event_type="sessionStart")
    queue.enqueue(record, retry_count=1, last_error="http_500")

    summary = queue.process_pending(
        _Sender(HttpSendResult(success=False, retryable=True, status_code=503, error="http_503"))
    )

    assert summary.retryable == 1
    assert summary.remaining == 1
    pending = _jsonl(queue.pending_path)
    assert pending[0]["event_id"] == record.event_id
    assert pending[0]["retry_count"] == 2
