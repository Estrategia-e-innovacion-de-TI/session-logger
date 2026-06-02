from fastapi.testclient import TestClient

from app.config.settings import BackendSettings
from app.main import create_app

from conftest import AppTestContainer


def _client():
    settings = BackendSettings(
        api_keys=("dev-token",),
        database_url="postgresql+psycopg://unused",
        max_body_mb=2,
        allow_unknown_event_types=False,
        query_limit=100,
        analytics_limit=100,
        auto_migrate=False,
    )
    return TestClient(create_app(settings, AppTestContainer(settings)))


def test_health_returns_storage() -> None:
    with _client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "storage": "postgres"}


def test_post_without_token_fails(sample_event_dict) -> None:
    with _client() as client:
        response = client.post("/api/v1/events", json=sample_event_dict)

    assert response.status_code == 401


def test_post_with_valid_token_persists_idempotently_and_query_returns_event(sample_event_dict) -> None:
    headers = {"Authorization": "Bearer dev-token"}
    with _client() as client:
        first_post = client.post("/api/v1/events", json=sample_event_dict, headers=headers)
        second_post = client.post("/api/v1/events", json=sample_event_dict, headers=headers)
        query_response = client.get("/api/v1/events", headers=headers)

    assert first_post.status_code == 202
    assert first_post.json()["created"] is True
    assert second_post.status_code == 202
    assert second_post.json()["created"] is False
    assert query_response.status_code == 200
    payload = query_response.json()
    assert payload["count"] == 1
    assert payload["events"][0]["event_id"] == "event-1"


def test_post_accepts_x_logger_token_and_normalized_shell_contract(sample_event_dict) -> None:
    event = dict(sample_event_dict)
    event.update(
        {
            "event_id": "evt-shell-1",
            "event_type": "tool_use",
            "source": "github_copilot_hook",
            "actor": "developer",
            "user_id": "developer",
            "mode": "agent",
            "execution_mode": "sync",
            "invocation_origin": "custom_agent",
            "userPrompt_id": None,
            "parent_userPrompt_id": "up-shell-1",
            "tool_name": "bash",
            "tool_input_summary": "rg --files",
            "files_added": ["backend/app/new_module.py"],
        }
    )

    with _client() as client:
        response = client.post("/api/v1/events", json=event, headers={"X-Logger-Token": "dev-token"})
        query_response = client.get("/api/v1/events", headers={"X-Logger-Token": "dev-token"})

    assert response.status_code == 202
    stored = query_response.json()["events"][0]
    assert stored["event_type"] == "tool_use"
    assert stored["source"] == "github_copilot_hook"
    assert stored["actor"] == "developer"
    assert stored["mode"] == "agent"
    assert stored["execution_mode"] == "sync"
    assert stored["invocation_origin"] == "custom_agent"
    assert stored["files_added"] == ["backend/app/new_module.py"]


def test_batch_ingest_accepts_valid_and_rejects_unknown(sample_event_dict) -> None:
    headers = {"Authorization": "Bearer dev-token"}
    second = dict(sample_event_dict)
    second["event_id"] = "event-2"
    second["event_type"] = "sessionStart"
    unknown = dict(sample_event_dict)
    unknown["event_id"] = "event-3"
    unknown["event_type"] = "unknownEvent"

    with _client() as client:
        response = client.post(
            "/api/v1/events/batch",
            json={"events": [sample_event_dict, second, unknown]},
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] == 2
    assert payload["created"] == 2
    assert payload["rejected"] == 1
    assert payload["errors"][0]["event_id"] == "event-3"


def test_api_resanitizes_before_persisting(sample_event_dict) -> None:
    headers = {"Authorization": "Bearer dev-token"}
    event = dict(sample_event_dict)
    event["prompt_text"] = "Use sk-proj-abcdefghijklmnopqrstuvwxyz123456"
    event["raw_payload"] = {"password": "super-secret"}

    with _client() as client:
        client.post("/api/v1/events", json=event, headers=headers)
        response = client.get("/api/v1/events", headers=headers)

    stored = response.json()["events"][0]
    assert stored["prompt_text"] == "Use [REDACTED:OPENAI_KEY]"
    assert stored["raw_payload"]["password"] == "[REDACTED]"


def test_prompt_trace_endpoint_uses_prompt_parent_relationship(sample_event_dict) -> None:
    headers = {"Authorization": "Bearer dev-token"}
    child = dict(sample_event_dict)
    child.update(
        {
            "event_id": "event-2",
            "event_type": "preToolUse",
            "userPrompt_id": None,
            "parent_userPrompt_id": "prompt-1",
            "tool_name": "bash",
        }
    )

    with _client() as client:
        client.post("/api/v1/events/batch", json={"events": [sample_event_dict, child]}, headers=headers)
        response = client.get("/api/v1/prompts/prompt-1/trace", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["userPrompt_id"] == "prompt-1"
    assert payload["event_count"] == 2


def test_analytics_endpoints_are_available(sample_event_dict) -> None:
    headers = {"Authorization": "Bearer dev-token"}
    tool_event = dict(sample_event_dict)
    tool_event.update(
        {
            "event_id": "event-2",
            "event_type": "postToolUse",
            "tool_name": "bash",
            "status": "success",
            "parent_userPrompt_id": "prompt-1",
            "commands_executed": ["pytest"],
            "files_touched": ["app/main.py"],
        }
    )

    with _client() as client:
        client.post("/api/v1/events/batch", json={"events": [sample_event_dict, tool_event]}, headers=headers)
        tool_usage = client.get("/api/v1/analytics/tool-usage", headers=headers)
        repo_activity = client.get("/api/v1/analytics/repository-activity", headers=headers)
        prompt_impact = client.get("/api/v1/analytics/prompt-impact", headers=headers)
        session_summary = client.get("/api/v1/analytics/session-summary", headers=headers)

    assert tool_usage.status_code == 200
    assert repo_activity.status_code == 200
    assert prompt_impact.status_code == 200
    assert session_summary.status_code == 200
    assert tool_usage.json()["items"][0]["tool_name"] == "bash"
