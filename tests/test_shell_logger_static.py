from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_shell_logger_exposes_expected_functions() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "lib/logger.sh",
            ROOT / "lib/payload.sh",
            ROOT / "lib/state.sh",
            ROOT / "lib/transport.sh",
        ]
    )

    for function_name in (
        "read_stdin_payload",
        "validate_dependencies",
        "extract_event_type",
        "extract_session_id",
        "extract_user_prompt",
        "extract_tool_metadata",
        "generate_event_id",
        "generate_userPrompt_id",
        "get_last_userPrompt_id",
        "set_last_userPrompt_id",
        "resolve_parent_userPrompt_id",
        "build_normalized_event",
        "write_jsonl_event",
        "send_event_to_api",
        "sanitize_payload",
    ):
        assert f"{function_name}()" in source


def test_shell_logger_uses_jq_for_json_construction() -> None:
    source = (ROOT / "lib/payload.sh").read_text(encoding="utf-8")
    assert "jq -cn" in source
    assert "gsub(" in source
    assert "raw_payload:$payload" in source


def test_new_examples_are_valid_json() -> None:
    for filename in (
        "payload-user-prompt.json",
        "payload-tool-use.json",
        "payload-tool-result.json",
    ):
        data = json.loads((ROOT / "examples" / filename).read_text(encoding="utf-8"))
        assert data["sessionId"] == "sess_demo_001"


@pytest.mark.skipif(
    not (shutil.which("bash") and shutil.which("jq") and shutil.which("curl")),
    reason="bash, jq and curl are required for the shell integration test",
)
def test_shell_logger_dry_run_correlates_prompt_and_tool(tmp_path) -> None:
    env = {
        "COPILOT_SESSION_LOGGER_HOME": str(tmp_path / ".session-logger"),
        "COPILOT_SESSION_LOGGER_HTTP_ENABLED": "false",
        "COPILOT_SESSION_LOGGER_STRICT": "true",
    }
    prompt = subprocess.run(
        ["bash", str(ROOT / "hooks/session-logger.sh"), "--event", "userPromptSubmitted"],
        input=(ROOT / "examples/payload-user-prompt.json").read_text(encoding="utf-8"),
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    assert prompt.stdout == ""

    tool = subprocess.run(
        ["bash", str(ROOT / "hooks/session-logger.sh"), "--event", "preToolUse", "--dry-run"],
        input=(ROOT / "examples/payload-tool-use.json").read_text(encoding="utf-8"),
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    tool_event = json.loads(tool.stdout)
    assert tool_event["event_type"] == "tool_use"
    assert tool_event["parent_userPrompt_id"].startswith("up_")
