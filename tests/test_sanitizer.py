from copilot_session_logger.sanitizer import sanitize_value


def test_sanitize_value_redacts_nested_secrets() -> None:
    payload = {
        "prompt": "token github_pat_abcdefghijklmnopqrstuvwxyz123456",
        "password": "super-secret",
        "nested": {
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def",
            "openai_key": "sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        },
    }

    sanitized = sanitize_value(payload)

    assert sanitized["prompt"] == "token [REDACTED:GITHUB_TOKEN]"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["nested"]["Authorization"] == "[REDACTED]"
    assert sanitized["nested"]["openai_key"] == "[REDACTED]"


def test_sanitize_value_redacts_private_keys() -> None:
    private_key = """-----BEGIN PRIVATE KEY-----
abc123
-----END PRIVATE KEY-----"""

    sanitized = sanitize_value({"pem": private_key})

    assert sanitized["pem"] == "[REDACTED:PRIVATE_KEY]"

