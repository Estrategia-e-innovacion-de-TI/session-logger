from app.driven_adapters.security.sanitizer import RegexSanitizer


def test_sanitizer_redacts_common_secret_shapes() -> None:
    sanitizer = RegexSanitizer()
    payload = {
        "prompt": "token github_pat_abcdefghijklmnopqrstuvwxyz123456",
        "password": "super-secret",
        "nested": {
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def",
            "openai_key": "sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        },
    }

    sanitized = sanitizer.sanitize(payload)

    assert sanitized["prompt"] == "token [REDACTED:GITHUB_TOKEN]"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["nested"]["Authorization"] == "[REDACTED]"
    assert sanitized["nested"]["openai_key"] == "[REDACTED]"


def test_sanitizer_redacts_private_keys() -> None:
    private_key = """-----BEGIN PRIVATE KEY-----
abc123
-----END PRIVATE KEY-----"""

    sanitized = RegexSanitizer().sanitize({"pem": private_key})

    assert sanitized["pem"] == "[REDACTED:PRIVATE_KEY]"
