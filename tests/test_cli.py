import json
from pathlib import Path

from typer.testing import CliRunner

from copilot_session_logger.cli import app

runner = CliRunner()


def test_log_dry_run_captures_prompt_and_sanitizes(tmp_path) -> None:
    home_dir = tmp_path / "home"
    payload = {
        "timestamp": 1704614460000,
        "cwd": str(tmp_path),
        "prompt": "token github_pat_abcdefghijklmnopqrstuvwxyz123456",
        "actor": "alice",
    }

    result = runner.invoke(
        app,
        ["log", "--event", "userPromptSubmitted", "--dry-run"],
        input=json.dumps(payload),
        env={"COPILOT_SESSION_LOGGER_HOME": str(home_dir)},
    )

    assert result.exit_code == 0, result.stdout
    event = json.loads(result.stdout)
    assert event["user_prompt"] == "token [REDACTED:GITHUB_TOKEN]"
    assert event["raw_payload"]["prompt"] == "token [REDACTED:GITHUB_TOKEN]"
    assert event["event_type"] == "userPromptSubmitted"


def test_log_writes_jsonl_and_reuses_session_id(tmp_path) -> None:
    home_dir = tmp_path / "home"
    session_start = {
        "timestamp": 1704614400000,
        "cwd": str(tmp_path),
        "source": "new",
    }
    prompt_event = {
        "timestamp": 1704614460000,
        "cwd": str(tmp_path),
        "prompt": "Explain this repo",
    }

    start_result = runner.invoke(
        app,
        ["log", "--event", "sessionStart"],
        input=json.dumps(session_start),
        env={"COPILOT_SESSION_LOGGER_HOME": str(home_dir)},
    )
    assert start_result.exit_code == 0, start_result.stdout

    dry_run_result = runner.invoke(
        app,
        ["log", "--event", "userPromptSubmitted", "--dry-run"],
        input=json.dumps(prompt_event),
        env={"COPILOT_SESSION_LOGGER_HOME": str(home_dir)},
    )
    assert dry_run_result.exit_code == 0, dry_run_result.stdout
    dry_run_event = json.loads(dry_run_result.stdout)

    log_files = list((home_dir / "logs").rglob("events.jsonl"))
    assert len(log_files) == 1

    persisted_event = json.loads(log_files[0].read_text(encoding="utf-8").strip())
    assert persisted_event["session_id"] == dry_run_event["session_id"]
    assert persisted_event["event_type"] == "sessionStart"


def test_doctor_outputs_json(tmp_path) -> None:
    home_dir = tmp_path / "home"

    result = runner.invoke(
        app,
        ["doctor"],
        env={"COPILOT_SESSION_LOGGER_HOME": str(home_dir)},
    )

    assert result.exit_code == 0, result.stdout
    report = json.loads(result.stdout)
    assert report["home_dir"] == str(home_dir)
    assert "git" in report


def test_demo_dry_run_returns_three_events(tmp_path) -> None:
    home_dir = tmp_path / "home"

    result = runner.invoke(
        app,
        ["demo", "--dry-run"],
        env={"COPILOT_SESSION_LOGGER_HOME": str(home_dir)},
    )

    assert result.exit_code == 0, result.stdout
    events = json.loads(result.stdout)
    assert len(events) == 3
    assert [event["event_type"] for event in events] == [
        "sessionStart",
        "userPromptSubmitted",
        "postToolUse",
    ]
