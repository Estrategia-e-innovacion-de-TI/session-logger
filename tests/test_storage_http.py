import json
from urllib.error import HTTPError

from copilot_session_logger.config import HttpConfig
from copilot_session_logger.schema import EventRecord
from copilot_session_logger.storage_http import HttpEventSender


def _http_config(tmp_path):
    return HttpConfig(
        enabled=True,
        endpoint="https://collector.example.test/v1/events",
        api_key="test-token",
        timeout_seconds=1.5,
        offline_queue_enabled=True,
        max_retries=3,
        queue_dir=tmp_path,
    )


class _Response:
    def __init__(self, status):
        self.status = status

    def getcode(self):
        return self.status

    def close(self):
        pass


def test_http_success_posts_sanitized_json(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response(202)

    monkeypatch.setattr("copilot_session_logger.storage_http.urlopen", fake_urlopen)
    record = EventRecord(
        session_id="session-1",
        event_type="userPromptSubmitted",
        user_prompt="use sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        raw_payload={
            "prompt": "token ghp_abcdefghijklmnopqrstuvwxyz123456",
            "api_key": "plain-secret",
        },
    )

    result = HttpEventSender(_http_config(tmp_path)).send_event(record)

    assert result.success is True
    assert result.retryable is False
    assert captured["timeout"] == 1.5
    request = captured["request"]
    assert request.get_header("Authorization") == "Bearer test-token"
    assert request.get_header("X-event-id") == record.event_id
    body = json.loads(request.data.decode("utf-8"))
    assert body["user_prompt"] == "use [REDACTED:OPENAI_KEY]"
    assert body["raw_payload"]["prompt"] == "token [REDACTED:GITHUB_TOKEN]"
    assert body["raw_payload"]["api_key"] == "[REDACTED]"


def test_http_401_is_not_retryable(monkeypatch, tmp_path) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr("copilot_session_logger.storage_http.urlopen", fake_urlopen)

    result = HttpEventSender(_http_config(tmp_path)).send_event(
        EventRecord(session_id="session-1", event_type="sessionStart")
    )

    assert result.success is False
    assert result.retryable is False
    assert result.status_code == 401


def test_http_500_is_retryable(monkeypatch, tmp_path) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 500, "Server Error", hdrs=None, fp=None)

    monkeypatch.setattr("copilot_session_logger.storage_http.urlopen", fake_urlopen)

    result = HttpEventSender(_http_config(tmp_path)).send_event(
        EventRecord(session_id="session-1", event_type="sessionStart")
    )

    assert result.success is False
    assert result.retryable is True
    assert result.status_code == 500


def test_http_timeout_is_retryable(monkeypatch, tmp_path) -> None:
    def fake_urlopen(request, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr("copilot_session_logger.storage_http.urlopen", fake_urlopen)

    result = HttpEventSender(_http_config(tmp_path)).send_event(
        EventRecord(session_id="session-1", event_type="sessionStart")
    )

    assert result.success is False
    assert result.retryable is True
    assert result.error == "TimeoutError"
