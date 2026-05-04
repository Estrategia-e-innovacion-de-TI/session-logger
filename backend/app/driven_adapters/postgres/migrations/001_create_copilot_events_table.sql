CREATE TABLE IF NOT EXISTS copilot_events (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    user_id TEXT NULL,
    repository TEXT NULL,
    branch TEXT NULL,
    workspace TEXT NULL,
    "userPrompt_id" TEXT NULL,
    "parent_userPrompt_id" TEXT NULL,
    tool_name TEXT NULL,
    prompt_text TEXT NULL,
    assistant_response_summary TEXT NULL,
    tool_input_summary TEXT NULL,
    tool_result_summary TEXT NULL,
    status TEXT NULL,
    duration_ms INTEGER NULL,
    files_touched JSONB NOT NULL DEFAULT '[]'::jsonb,
    commands_executed JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_payload JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_copilot_events_event_id ON copilot_events (event_id);
CREATE INDEX IF NOT EXISTS idx_copilot_events_session_id ON copilot_events (session_id);
CREATE INDEX IF NOT EXISTS idx_copilot_events_timestamp ON copilot_events (timestamp);
CREATE INDEX IF NOT EXISTS idx_copilot_events_event_type ON copilot_events (event_type);
CREATE INDEX IF NOT EXISTS idx_copilot_events_repository ON copilot_events (repository);
CREATE INDEX IF NOT EXISTS idx_copilot_events_userPrompt_id ON copilot_events ("userPrompt_id");
CREATE INDEX IF NOT EXISTS idx_copilot_events_parent_userPrompt_id ON copilot_events ("parent_userPrompt_id");
CREATE INDEX IF NOT EXISTS idx_copilot_events_tool_name ON copilot_events (tool_name);
CREATE INDEX IF NOT EXISTS idx_copilot_events_repository_timestamp ON copilot_events (repository, timestamp);
CREATE INDEX IF NOT EXISTS idx_copilot_events_parent_prompt_event_type
    ON copilot_events ("parent_userPrompt_id", event_type);
CREATE INDEX IF NOT EXISTS idx_copilot_events_metadata_gin ON copilot_events USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_copilot_events_raw_payload_gin ON copilot_events USING GIN (raw_payload);

