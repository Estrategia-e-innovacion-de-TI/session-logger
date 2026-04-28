CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    user_prompt TEXT NULL,
    prompt_hash TEXT NULL,
    repo_path TEXT NULL,
    repo_name TEXT NULL,
    git_branch TEXT NULL,
    git_commit TEXT NULL,
    working_directory TEXT NULL,
    actor TEXT NULL,
    files_changed JSONB NOT NULL DEFAULT '[]'::jsonb,
    tool_name TEXT NULL,
    command TEXT NULL,
    status TEXT NULL,
    error TEXT NULL,
    raw_payload JSONB NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_session_id ON events (session_id);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_repo_name ON events (repo_name);
CREATE INDEX IF NOT EXISTS idx_events_actor ON events (actor);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events (timestamp);
CREATE INDEX IF NOT EXISTS idx_events_prompt_hash ON events (prompt_hash);
