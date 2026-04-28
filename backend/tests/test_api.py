import json


def _stored_events(home):
    events = []
    for path in home.glob("events/*/events.jsonl"):
        events.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return events


def test_health(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_post_with_valid_token_accepts_event(client, auth_headers, sample_event, backend_home) -> None:
    response = client.post("/v1/events", json=sample_event, headers=auth_headers)

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    stored = _stored_events(backend_home)
    assert stored[0]["event_id"] == "event-1"
    assert stored[0]["event_type"] == "userPromptSubmitted"


def test_post_with_invalid_schema_returns_422(client, auth_headers) -> None:
    response = client.post(
        "/v1/events",
        json={"event_type": "userPromptSubmitted"},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_batch_accepts_valid_events_and_rejects_invalid(client, auth_headers, sample_event) -> None:
    second = dict(sample_event)
    second["event_id"] = "event-2"
    second["event_type"] = "sessionStart"
    unknown = dict(sample_event)
    unknown["event_id"] = "event-3"
    unknown["event_type"] = "unknownEvent"

    response = client.post(
        "/v1/events/batch",
        json={"events": [sample_event, second, unknown]},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] == 2
    assert payload["rejected"] == 1


def test_query_events_filters_by_repo_and_actor(client, auth_headers, sample_event) -> None:
    client.post("/v1/events", json=sample_event, headers=auth_headers)

    response = client.get(
        "/v1/events",
        params={"repo_name": "demo-repo", "actor": "alice", "limit": 10},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["events"][0]["event_id"] == "event-1"


def test_backend_resanitizes_payload_before_storage(client, auth_headers, sample_event, backend_home) -> None:
    event = dict(sample_event)
    event["event_id"] = "event-secret"
    event["user_prompt"] = "Use sk-proj-abcdefghijklmnopqrstuvwxyz123456"
    event["raw_payload"] = {
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def",
        "password": "super-secret",
    }

    response = client.post("/v1/events", json=event, headers=auth_headers)

    assert response.status_code == 202
    stored = _stored_events(backend_home)[0]
    assert stored["user_prompt"] == "Use [REDACTED:OPENAI_KEY]"
    assert stored["raw_payload"]["Authorization"] == "[REDACTED]"
    assert stored["raw_payload"]["password"] == "[REDACTED]"


def test_sqlite_storage_resanitizes_payload(monkeypatch, tmp_path, auth_headers, sample_event) -> None:
    from fastapi.testclient import TestClient

    from copilot_log_backend.main import app

    home = tmp_path / "sqlite-home"
    monkeypatch.setenv("COPILOT_LOG_BACKEND_API_KEYS", "dev-token")
    monkeypatch.setenv("COPILOT_LOG_BACKEND_STORAGE", "sqlite")
    monkeypatch.setenv("COPILOT_LOG_BACKEND_HOME", str(home))
    event = dict(sample_event)
    event["event_id"] = "sqlite-secret"
    event["raw_payload"] = {"api_key": "plain-secret"}

    with TestClient(app) as sqlite_client:
        response = sqlite_client.post("/v1/events", json=event, headers=auth_headers)
        query = sqlite_client.get("/v1/events", headers=auth_headers)

    assert response.status_code == 202
    assert query.status_code == 200
    assert query.json()["events"][0]["raw_payload"]["api_key"] == "[REDACTED]"
