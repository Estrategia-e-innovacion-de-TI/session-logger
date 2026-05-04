from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.domain.model.copilot_event import CopilotEvent
from app.driven_adapters.postgres.database import (
    create_postgres_engine,
    create_session_factory,
    run_migrations,
)
from app.driven_adapters.postgres.event_repository_adapter import PostgresEventRepository


@pytest.mark.skipif(
    not os.getenv("COPILOT_LOG_BACKEND_TEST_DATABASE_URL"),
    reason="COPILOT_LOG_BACKEND_TEST_DATABASE_URL is required for PostgreSQL adapter integration tests",
)
def test_postgres_adapter_persists_idempotently_and_resolves_prompt_trace() -> None:
    engine = create_postgres_engine(os.environ["COPILOT_LOG_BACKEND_TEST_DATABASE_URL"])
    run_migrations(engine)
    repository = PostgresEventRepository(create_session_factory(engine))
    suffix = uuid4().hex
    event_id = f"event-{suffix}"
    child_id = f"child-{suffix}"
    prompt_id = f"prompt-{suffix}"

    root = CopilotEvent.new(
        event_id=event_id,
        session_id=f"session-{suffix}",
        event_type="userPromptSubmitted",
        user_prompt_id=prompt_id,
        prompt_text="Explain this code",
        repository="demo-repo",
    )
    child = CopilotEvent.new(
        event_id=child_id,
        session_id=root.session_id,
        event_type="postToolUse",
        parent_user_prompt_id=prompt_id,
        tool_name="bash",
        status="success",
    )

    try:
        first = repository.save(root)
        second = repository.save(root)
        repository.save(child)

        assert first.event_id == second.event_id
        assert len(repository.find_by_session_id(root.session_id)) == 2
        assert repository.find_by_parent_userPrompt_id(prompt_id)[0].event_id == child_id
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM copilot_events WHERE event_id IN (:root_id, :child_id)"),
                {"root_id": event_id, "child_id": child_id},
            )
