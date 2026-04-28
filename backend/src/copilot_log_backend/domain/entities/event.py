from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

SUPPORTED_EVENT_TYPES = (
    "sessionStart",
    "userPromptSubmitted",
    "preToolUse",
    "postToolUse",
    "sessionEnd",
    "errorOccurred",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: Any) -> datetime:
    if value is None or value == "":
        return utc_now()
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number = number / 1000.0
        return datetime.fromtimestamp(number, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return utc_now()
        if text.isdigit():
            return parse_timestamp(int(text))
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise TypeError(f"Unsupported timestamp value: {value!r}")


def compute_prompt_hash(prompt: str | None) -> str | None:
    if prompt is None:
        return None
    return sha256(prompt.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class EventRecord:
    event_id: str
    session_id: str
    event_type: str
    timestamp: datetime
    user_prompt: str | None = None
    prompt_hash: str | None = None
    repo_path: str | None = None
    repo_name: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    working_directory: str | None = None
    actor: str | None = None
    files_changed: list[str] = field(default_factory=list)
    tool_name: str | None = None
    command: str | None = None
    status: str | None = None
    error: str | None = None
    raw_payload: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.timestamp = parse_timestamp(self.timestamp)
        self.created_at = parse_timestamp(self.created_at)
        self.files_changed = [str(item) for item in (self.files_changed or [])]
        self.metadata = self.metadata if isinstance(self.metadata, dict) else {"value": self.metadata}
        self.prompt_hash = compute_prompt_hash(self.user_prompt)

    @classmethod
    def new(
        cls,
        *,
        session_id: str,
        event_type: str,
        timestamp: Any = None,
        event_id: str | None = None,
        created_at: Any = None,
        **kwargs: Any,
    ) -> "EventRecord":
        return cls(
            event_id=event_id or str(uuid4()),
            session_id=session_id,
            event_type=event_type,
            timestamp=parse_timestamp(timestamp),
            created_at=parse_timestamp(created_at),
            **kwargs,
        )

    def with_sanitized_values(
        self,
        *,
        user_prompt: str | None,
        raw_payload: Any,
        metadata: dict[str, Any],
        command: str | None,
        error: str | None,
    ) -> "EventRecord":
        return replace(
            self,
            user_prompt=user_prompt,
            raw_payload=raw_payload,
            metadata=metadata,
            command=command,
            error=error,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "user_prompt": self.user_prompt,
            "prompt_hash": self.prompt_hash,
            "repo_path": self.repo_path,
            "repo_name": self.repo_name,
            "git_branch": self.git_branch,
            "git_commit": self.git_commit,
            "working_directory": self.working_directory,
            "actor": self.actor,
            "files_changed": list(self.files_changed),
            "tool_name": self.tool_name,
            "command": self.command,
            "status": self.status,
            "error": self.error,
            "raw_payload": self.raw_payload,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
        }
