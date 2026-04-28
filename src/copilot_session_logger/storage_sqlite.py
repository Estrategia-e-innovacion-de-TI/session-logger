from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .schema import EventRecord

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS event_records (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    user_prompt TEXT,
    prompt_hash TEXT,
    repo_path TEXT,
    repo_name TEXT,
    git_branch TEXT,
    git_commit TEXT,
    working_directory TEXT,
    actor TEXT,
    files_changed TEXT NOT NULL,
    tool_name TEXT,
    command TEXT,
    status TEXT,
    error TEXT,
    raw_payload TEXT,
    metadata TEXT NOT NULL
);
"""


class SQLiteEventWriter:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).expanduser()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(CREATE_TABLE_SQL)
            connection.commit()

    def write(self, event: EventRecord) -> Path:
        self.initialize()
        payload = event.to_jsonable()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO event_records (
                    event_id,
                    session_id,
                    event_type,
                    timestamp,
                    user_prompt,
                    prompt_hash,
                    repo_path,
                    repo_name,
                    git_branch,
                    git_commit,
                    working_directory,
                    actor,
                    files_changed,
                    tool_name,
                    command,
                    status,
                    error,
                    raw_payload,
                    metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["event_id"],
                    payload["session_id"],
                    payload["event_type"],
                    payload["timestamp"],
                    payload.get("user_prompt"),
                    payload.get("prompt_hash"),
                    payload.get("repo_path"),
                    payload.get("repo_name"),
                    payload.get("git_branch"),
                    payload.get("git_commit"),
                    payload.get("working_directory"),
                    payload.get("actor"),
                    json.dumps(payload.get("files_changed", []), ensure_ascii=True),
                    payload.get("tool_name"),
                    payload.get("command"),
                    payload.get("status"),
                    payload.get("error"),
                    json.dumps(payload.get("raw_payload"), ensure_ascii=True),
                    json.dumps(payload.get("metadata", {}), ensure_ascii=True),
                ),
            )
            connection.commit()
        return self.db_path

