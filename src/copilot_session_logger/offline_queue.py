from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .sanitizer import sanitize_value
from .schema import EventRecord
from .storage_http import HttpSendResult

DEFAULT_PROCESS_LIMIT = 20


class EventSender(Protocol):
    def send_event(self, event: dict[str, Any]) -> HttpSendResult:
        ...


@dataclass(slots=True)
class QueueProcessSummary:
    attempted: int = 0
    sent: int = 0
    retryable: int = 0
    dead_lettered: int = 0
    remaining: int = 0
    invalid: int = 0

    def to_jsonable(self) -> dict[str, int]:
        return asdict(self)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result_error(result: HttpSendResult) -> str | None:
    if result.status_code is not None:
        return f"{result.error or 'http_error'}:{result.status_code}"
    return result.error


def _event_payload(event: EventRecord | dict[str, Any]) -> dict[str, Any]:
    payload = event.to_jsonable() if isinstance(event, EventRecord) else dict(event)
    sanitized = sanitize_value(payload)
    if not isinstance(sanitized, dict):
        raise TypeError("Queued event must serialize to a JSON object.")
    return sanitized


class OfflineQueue:
    def __init__(self, queue_dir: str | Path, max_retries: int = 3) -> None:
        self.queue_dir = Path(queue_dir).expanduser()
        self.max_retries = max_retries

    @property
    def pending_path(self) -> Path:
        return self.queue_dir / "pending.jsonl"

    @property
    def sent_path(self) -> Path:
        return self.queue_dir / "sent.jsonl"

    @property
    def dead_letter_path(self) -> Path:
        return self.queue_dir / "dead_letter.jsonl"

    def enqueue(
        self,
        event: EventRecord | dict[str, Any],
        *,
        retry_count: int = 0,
        last_error: str | None = None,
    ) -> Path:
        payload = _event_payload(event)
        entry = {
            "event_id": payload.get("event_id"),
            "event": payload,
            "retry_count": retry_count,
            "last_error": last_error,
            "queued_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
        self._append_jsonl(self.pending_path, entry)
        return self.pending_path

    def dead_letter(
        self,
        event: EventRecord | dict[str, Any],
        *,
        retry_count: int = 0,
        last_error: str | None = None,
    ) -> Path:
        payload = _event_payload(event)
        entry = {
            "event_id": payload.get("event_id"),
            "event": payload,
            "retry_count": retry_count,
            "last_error": last_error,
            "dead_lettered_at": _utc_now_iso(),
        }
        self._append_jsonl(self.dead_letter_path, entry)
        return self.dead_letter_path

    def process_pending(
        self,
        sender: EventSender,
        *,
        max_items: int = DEFAULT_PROCESS_LIMIT,
    ) -> QueueProcessSummary:
        limit = max(0, min(max_items, DEFAULT_PROCESS_LIMIT))
        summary = QueueProcessSummary()
        pending, invalid_entries = self._read_pending()

        for invalid_entry in invalid_entries:
            self._append_jsonl(self.dead_letter_path, invalid_entry)
        summary.invalid = len(invalid_entries)

        to_process = pending[:limit]
        remaining = pending[limit:]
        retry_later: list[dict[str, Any]] = []

        for entry in to_process:
            summary.attempted += 1
            event = entry.get("event")
            if not isinstance(event, dict):
                self._write_dead_entry(entry, "invalid_queue_entry")
                summary.dead_lettered += 1
                continue

            result = sender.send_event(event)
            if result.success:
                self._write_sent_entry(entry, result)
                summary.sent += 1
                continue

            retry_count = int(entry.get("retry_count") or 0)
            last_error = _result_error(result)
            if result.retryable:
                retry_count += 1
                entry["retry_count"] = retry_count
                entry["last_error"] = last_error
                entry["updated_at"] = _utc_now_iso()
                if retry_count >= self.max_retries:
                    self._write_dead_entry(entry, last_error)
                    summary.dead_lettered += 1
                else:
                    retry_later.append(entry)
                    summary.retryable += 1
                continue

            entry["last_error"] = last_error
            self._write_dead_entry(entry, last_error)
            summary.dead_lettered += 1

        new_pending = retry_later + remaining
        self._rewrite_jsonl(self.pending_path, new_pending)
        summary.remaining = len(new_pending)
        return summary

    def _read_pending(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        pending: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        if not self.pending_path.exists():
            return pending, invalid

        with self.pending_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    value = json.loads(text)
                except json.JSONDecodeError as exc:
                    invalid.append(
                        {
                            "event_id": None,
                            "event": None,
                            "retry_count": 0,
                            "last_error": f"invalid_json_line_{line_number}: {exc.msg}",
                            "dead_lettered_at": _utc_now_iso(),
                        }
                    )
                    continue
                if isinstance(value, dict):
                    pending.append(value)
                else:
                    invalid.append(
                        {
                            "event_id": None,
                            "event": None,
                            "retry_count": 0,
                            "last_error": f"invalid_non_object_line_{line_number}",
                            "dead_lettered_at": _utc_now_iso(),
                        }
                    )
        return pending, invalid

    def _write_sent_entry(self, entry: dict[str, Any], result: HttpSendResult) -> None:
        sent_entry = dict(entry)
        sent_entry["sent_at"] = _utc_now_iso()
        sent_entry["http_result"] = result.to_jsonable()
        self._append_jsonl(self.sent_path, sent_entry)

    def _write_dead_entry(self, entry: dict[str, Any], last_error: str | None) -> None:
        dead_entry = dict(entry)
        dead_entry["last_error"] = last_error
        dead_entry["dead_lettered_at"] = _utc_now_iso()
        self._append_jsonl(self.dead_letter_path, dead_entry)

    def _append_jsonl(self, path: Path, entry: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(sanitize_value(entry), ensure_ascii=True, sort_keys=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _rewrite_jsonl(self, path: Path, entries: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            for entry in entries:
                handle.write(json.dumps(sanitize_value(entry), ensure_ascii=True, sort_keys=True))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
