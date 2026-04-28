from __future__ import annotations

import json
from pathlib import Path

from .schema import EventRecord


class JsonlEventWriter:
    def __init__(self, logs_dir: str | Path) -> None:
        self.logs_dir = Path(logs_dir).expanduser()

    def path_for_event(self, event: EventRecord) -> Path:
        date_dir = event.timestamp.date().isoformat()
        return self.logs_dir / date_dir / "events.jsonl"

    def write(self, event: EventRecord) -> Path:
        output_path = self.path_for_event(event)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event.to_jsonable(), ensure_ascii=True, sort_keys=True))
            handle.write("\n")
        return output_path

