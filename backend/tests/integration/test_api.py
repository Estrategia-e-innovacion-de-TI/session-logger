from fastapi.testclient import TestClient

from copilot_log_backend.application.config import BackendConfig
from copilot_log_backend.entrypoints.api.app import create_app


def _client(tmp_path):
    config = BackendConfig(
        api_keys=("dev-token",),
        database_url="postgresql+psycopg://unused",
        storage="jsonl",
        max_body_mb=2,
        allow_unknown_event_types=False,
        query_limit=100,
        home_dir=tmp_path,
        auto_migrate=False,
    )
    return TestClient(create_app(config))


def test_health_returns_storage(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "storage": "jsonl"}


def test_post_without_token_fails(tmp_path, sample_event_dict) -> None:
    with _client(tmp_path) as client:
        response = client.post("/v1/events", json=sample_event_dict)

    assert response.status_code == 401


def test_post_with_valid_token_persists_and_query_returns_event(tmp_path, sample_event_dict) -> None:
    headers = {"Authorization": "Bearer dev-token"}
    with _client(tmp_path) as client:
        post_response = client.post("/v1/events", json=sample_event_dict, headers=headers)
        query_response = client.get("/v1/events", headers=headers)

    assert post_response.status_code == 202
    assert post_response.json()["status"] == "accepted"
    assert query_response.status_code == 200
    payload = query_response.json()
    assert payload["count"] == 1
    assert payload["events"][0]["event_id"] == "event-1"


def test_batch_ingest_accepts_valid_and_rejects_unknown(tmp_path, sample_event_dict) -> None:
    headers = {"Authorization": "Bearer dev-token"}
    second = dict(sample_event_dict)
    second["event_id"] = "event-2"
    second["event_type"] = "sessionStart"
    unknown = dict(sample_event_dict)
    unknown["event_id"] = "event-3"
    unknown["event_type"] = "unknownEvent"

    with _client(tmp_path) as client:
        response = client.post(
            "/v1/events/batch",
            json={"events": [sample_event_dict, second, unknown]},
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] == 2
    assert payload["rejected"] == 1
    assert payload["errors"][0]["event_id"] == "event-3"


def test_api_resanitizes_before_persisting(tmp_path, sample_event_dict) -> None:
    headers = {"Authorization": "Bearer dev-token"}
    event = dict(sample_event_dict)
    event["user_prompt"] = "Use sk-proj-abcdefghijklmnopqrstuvwxyz123456"
    event["raw_payload"] = {"password": "super-secret"}

    with _client(tmp_path) as client:
        client.post("/v1/events", json=event, headers=headers)
        response = client.get("/v1/events", headers=headers)

    stored = response.json()["events"][0]
    assert stored["user_prompt"] == "Use [REDACTED:OPENAI_KEY]"
    assert stored["raw_payload"]["password"] == "[REDACTED]"
