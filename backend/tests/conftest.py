from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture()
def backend_home(monkeypatch, tmp_path):
    home = tmp_path / "backend-home"
    monkeypatch.setenv("COPILOT_LOG_BACKEND_API_KEYS", "dev-token,second-token")
    monkeypatch.setenv("COPILOT_LOG_BACKEND_STORAGE", "jsonl")
    monkeypatch.setenv("COPILOT_LOG_BACKEND_HOME", str(home))
    monkeypatch.setenv("COPILOT_LOG_BACKEND_MAX_BODY_MB", "2")
    monkeypatch.delenv("ALLOW_UNKNOWN_EVENT_TYPES", raising=False)
    monkeypatch.delenv("COPILOT_LOG_BACKEND_ALLOW_UNKNOWN_EVENT_TYPES", raising=False)
    return home


@pytest.fixture()
def client(backend_home):
    from copilot_log_backend.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers():
    return {"Authorization": "Bearer dev-token"}


@pytest.fixture()
def sample_event():
    return {
        "event_id": "event-1",
        "session_id": "session-1",
        "event_type": "userPromptSubmitted",
        "timestamp": 1704614500000,
        "user_prompt": "Explain this code",
        "repo_name": "demo-repo",
        "actor": "alice",
        "raw_payload": {"prompt": "Explain this code"},
        "metadata": {"source": "test"},
    }
