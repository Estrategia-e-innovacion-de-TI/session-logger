import json

from typer.testing import CliRunner

from copilot_session_logger.cli import app
from copilot_session_logger.storage_http import HttpSendResult

runner = CliRunner()


def _env(home_dir):
    return {
        "COPILOT_SESSION_LOGGER_HOME": str(home_dir),
        "COPILOT_SESSION_LOGGER_HTTP_ENABLED": "true",
        "COPILOT_SESSION_LOGGER_ENDPOINT": "https://collector.example.test/v1/events",
        "COPILOT_SESSION_LOGGER_API_KEY": "test-token",
    }


def _jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_log_queues_retryable_http_failure_and_flush_sends(monkeypatch, tmp_path) -> None:
    home_dir = tmp_path / "home"

    class FailingSender:
        def __init__(self, config):
            pass

        def send_event(self, event):
            return HttpSendResult(success=False, retryable=True, status_code=500, error="http_500")

    monkeypatch.setattr("copilot_session_logger.cli.HttpEventSender", FailingSender)
    result = runner.invoke(
        app,
        ["log", "--event", "userPromptSubmitted"],
        input=json.dumps({"cwd": str(tmp_path), "prompt": "hello"}),
        env=_env(home_dir),
    )

    assert result.exit_code == 0, result.stdout
    pending_path = home_dir / "queue" / "pending.jsonl"
    assert len(_jsonl(pending_path)) == 1

    class SuccessSender:
        def __init__(self, config):
            pass

        def send_event(self, event):
            return HttpSendResult(success=True, retryable=False, status_code=202)

    monkeypatch.setattr("copilot_session_logger.cli.HttpEventSender", SuccessSender)
    flush_result = runner.invoke(app, ["flush"], env=_env(home_dir))

    assert flush_result.exit_code == 0, flush_result.stdout
    assert _jsonl(pending_path) == []
    assert len(_jsonl(home_dir / "queue" / "sent.jsonl")) == 1


def test_log_moves_non_retryable_http_failure_to_dead_letter(monkeypatch, tmp_path) -> None:
    home_dir = tmp_path / "home"

    class AuthFailSender:
        def __init__(self, config):
            pass

        def send_event(self, event):
            return HttpSendResult(success=False, retryable=False, status_code=401, error="http_401")

    monkeypatch.setattr("copilot_session_logger.cli.HttpEventSender", AuthFailSender)

    result = runner.invoke(
        app,
        ["log", "--event", "userPromptSubmitted"],
        input=json.dumps({"cwd": str(tmp_path), "prompt": "hello"}),
        env=_env(home_dir),
    )

    assert result.exit_code == 0, result.stdout
    assert _jsonl(home_dir / "queue" / "pending.jsonl") == []
    dead = _jsonl(home_dir / "queue" / "dead_letter.jsonl")
    assert len(dead) == 1
    assert dead[0]["last_error"] == "http_401:401"
