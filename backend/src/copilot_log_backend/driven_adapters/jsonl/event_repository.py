from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from copilot_log_backend.domain.entities.event import EventRecord, parse_timestamp


class JsonlEventRepository:
    def __init__(self, events_dir: str | Path) -> None:
        self.events_dir = Path(events_dir).expanduser()

    def save(self, event: EventRecord) -> EventRecord:
        output_path = self._path_for_event(event)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=True, sort_keys=True))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return event

    def save_many(self, events: list[EventRecord]) -> list[EventRecord]:
        for event in events:
            self.save(event)
        return events

    def find(
        self,
        *,
        session_id: str | None,
        event_type: str | None,
        repo_name: str | None,
        actor: str | None,
        from_timestamp: str | None,
        to_timestamp: str | None,
        limit: int,
    ) -> list[EventRecord]:
        from_dt = parse_timestamp(from_timestamp) if from_timestamp else None
        to_dt = parse_timestamp(to_timestamp) if to_timestamp else None
        events: list[EventRecord] = []

        for path in sorted(self.events_dir.glob("*/events.jsonl")):
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        data = json.loads(text)
                        event = _event_from_dict(data)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        continue
                    if _matches(
                        event,
                        session_id=session_id,
                        event_type=event_type,
                        repo_name=repo_name,
                        actor=actor,
                        from_dt=from_dt,
                        to_dt=to_dt,
                    ):
                        events.append(event)

        events.sort(key=lambda item: item.timestamp, reverse=True)
        return events[:limit]

    def health(self) -> bool:
        self.events_dir.mkdir(parents=True, exist_ok=True)
        return self.events_dir.exists()

    def _path_for_event(self, event: EventRecord) -> Path:
        return self.events_dir / event.timestamp.date().isoformat() / "events.jsonl"


def _event_from_dict(data: dict[str, Any]) -> EventRecord:
    return EventRecord(
        event_id=str(data["event_id"]),
        session_id=str(data["session_id"]),
        event_type=str(data["event_type"]),
        timestamp=data["timestamp"],
        user_prompt=data.get("user_prompt"),
        prompt_hash=data.get("prompt_hash"),
        repo_path=data.get("repo_path"),
        repo_name=data.get("repo_name"),
        git_branch=data.get("git_branch"),
        git_commit=data.get("git_commit"),
        working_directory=data.get("working_directory"),
        actor=data.get("actor"),
        files_changed=data.get("files_changed") or [],
        tool_name=data.get("tool_name"),
        command=data.get("command"),
        status=data.get("status"),
        error=data.get("error"),
        raw_payload=data.get("raw_payload"),
        metadata=data.get("metadata") or {},
        created_at=data.get("created_at"),
    )


def _matches(
    event: EventRecord,
    *,
    session_id: str | None,
    event_type: str | None,
    repo_name: str | None,
    actor: str | None,
    from_dt: datetime | None,
    to_dt: datetime | None,
) -> bool:
    if session_id and event.session_id != session_id:
        return False
    if event_type and event.event_type != event_type:
        return False
    if repo_name and event.repo_name != repo_name:
        return False
    if actor and event.actor != actor:
        return False
    if from_dt and event.timestamp < from_dt:
        return False
    if to_dt and event.timestamp > to_dt:
        return False
    return True
