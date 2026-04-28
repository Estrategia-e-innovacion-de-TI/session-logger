from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..sanitizer import sanitize_value

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

INSERT_SQL = """
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
"""

SELECT_COLUMNS = (
    "event_id",
    "session_id",
    "event_type",
    "timestamp",
    "user_prompt",
    "prompt_hash",
    "repo_path",
    "repo_name",
    "git_branch",
    "git_commit",
    "working_directory",
    "actor",
    "files_changed",
    "tool_name",
    "command",
    "status",
    "error",
    "raw_payload",
    "metadata",
)


class SQLiteEventStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).expanduser()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(CREATE_TABLE_SQL)
            connection.commit()

    def write_event(self, event: dict[str, Any]) -> Path:
        self.initialize()
        payload = sanitize_value(event)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                INSERT_SQL,
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

    def query_events(
        self,
        *,
        session_id: str | None = None,
        event_type: str | None = None,
        repo_name: str | None = None,
        actor: str | None = None,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.initialize()
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("session_id", session_id),
            ("event_type", event_type),
            ("repo_name", repo_name),
            ("actor", actor),
        ):
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        if from_timestamp:
            clauses.append("timestamp >= ?")
            params.append(from_timestamp)
        if to_timestamp:
            clauses.append("timestamp <= ?")
            params.append(to_timestamp)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            f"SELECT {', '.join(SELECT_COLUMNS)} FROM event_records "
            f"{where_clause} ORDER BY timestamp DESC LIMIT ?"
        )
        params.append(limit)
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [_row_to_event(row) for row in rows]


def _row_to_event(row: tuple[Any, ...]) -> dict[str, Any]:
    event = dict(zip(SELECT_COLUMNS, row, strict=True))
    event["files_changed"] = json.loads(event["files_changed"] or "[]")
    event["raw_payload"] = json.loads(event["raw_payload"]) if event["raw_payload"] else None
    event["metadata"] = json.loads(event["metadata"] or "{}")
    return event
