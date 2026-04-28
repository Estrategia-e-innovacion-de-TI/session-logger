from copilot_log_backend.auth import token_is_valid
from copilot_log_backend.config import BackendConfig


def test_post_without_token_returns_401(client, sample_event) -> None:
    response = client.post("/v1/events", json=sample_event)

    assert response.status_code == 401


def test_post_with_invalid_token_returns_403(client, sample_event) -> None:
    response = client.post(
        "/v1/events",
        json=sample_event,
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 403


def test_token_is_valid_uses_configured_keys(tmp_path) -> None:
    config = BackendConfig(api_keys=("key1", "key2"), home_dir=tmp_path)

    assert token_is_valid("key1", config) is True
    assert token_is_valid("missing", config) is False
