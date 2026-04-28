from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..sanitizer import sanitize_value
from ..schema import parse_timestamp


class JsonlEventStorage:
    def __init__(self, events_dir: str | Path) -> None:
        self.events_dir = Path(events_dir).expanduser()

    def path_for_event(self, event: dict[str, Any]) -> Path:
        timestamp = parse_timestamp(event.get("timestamp"))
        return self.events_dir / timestamp.date().isoformat() / "events.jsonl"

    def write_event(self, event: dict[str, Any]) -> Path:
        output_path = self.path_for_event(event)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(sanitize_value(event), ensure_ascii=True, sort_keys=True)
        with output_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return output_path

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
        from_dt = parse_timestamp(from_timestamp) if from_timestamp else None
        to_dt = parse_timestamp(to_timestamp) if to_timestamp else None
        events: list[dict[str, Any]] = []

        for path in sorted(self.events_dir.glob("*/events.jsonl")):
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        event = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict) or not _matches(
                        event,
                        session_id=session_id,
                        event_type=event_type,
                        repo_name=repo_name,
                        actor=actor,
                        from_dt=from_dt,
                        to_dt=to_dt,
                    ):
                        continue
                    events.append(event)

        events.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
        return events[:limit]


def _matches(
    event: dict[str, Any],
    *,
    session_id: str | None,
    event_type: str | None,
    repo_name: str | None,
    actor: str | None,
    from_dt,
    to_dt,
) -> bool:
    if session_id and event.get("session_id") != session_id:
        return False
    if event_type and event.get("event_type") != event_type:
        return False
    if repo_name and event.get("repo_name") != repo_name:
        return False
    if actor and event.get("actor") != actor:
        return False
    event_dt = parse_timestamp(event.get("timestamp"))
    if from_dt and event_dt < from_dt:
        return False
    if to_dt and event_dt > to_dt:
        return False
    return True
