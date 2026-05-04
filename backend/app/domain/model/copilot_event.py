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
    "session_start",
    "user_prompt",
    "assistant_response",
    "tool_use",
    "tool_result",
    "command_execution",
    "file_edit",
    "error",
    "session_end",
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


def compute_prompt_hash(prompt_text: str | None) -> str | None:
    if prompt_text is None:
        return None
    return sha256(prompt_text.encode("utf-8")).hexdigest()


def _list_of_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


@dataclass(frozen=True, slots=True)
class EventFilters:
    session_id: str | None = None
    event_type: str | None = None
    repository: str | None = None
    user_id: str | None = None
    user_prompt_id: str | None = None
    parent_user_prompt_id: str | None = None
    tool_name: str | None = None
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None
    limit: int = 100

    def normalized(self, *, max_limit: int = 100) -> "EventFilters":
        return replace(
            self,
            from_timestamp=parse_timestamp(self.from_timestamp) if self.from_timestamp else None,
            to_timestamp=parse_timestamp(self.to_timestamp) if self.to_timestamp else None,
            limit=min(max(self.limit or max_limit, 1), max_limit),
        )


@dataclass(frozen=True, slots=True)
class CopilotEvent:
    event_id: str
    session_id: str
    event_type: str
    timestamp: datetime
    user_id: str | None = None
    repository: str | None = None
    branch: str | None = None
    workspace: str | None = None
    user_prompt_id: str | None = None
    parent_user_prompt_id: str | None = None
    tool_name: str | None = None
    prompt_text: str | None = None
    assistant_response_summary: str | None = None
    tool_input_summary: str | None = None
    tool_result_summary: str | None = None
    status: str | None = None
    duration_ms: int | None = None
    files_touched: list[str] = field(default_factory=list)
    commands_executed: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_payload: Any = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", parse_timestamp(self.timestamp))
        object.__setattr__(self, "created_at", parse_timestamp(self.created_at))
        object.__setattr__(self, "files_touched", _list_of_strings(self.files_touched))
        object.__setattr__(self, "commands_executed", _list_of_strings(self.commands_executed))
        metadata = self.metadata if isinstance(self.metadata, dict) else {"value": self.metadata}
        object.__setattr__(self, "metadata", metadata)
        if self.duration_ms is not None:
            object.__setattr__(self, "duration_ms", max(int(self.duration_ms), 0))

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
    ) -> "CopilotEvent":
        return cls(
            event_id=event_id or str(uuid4()),
            session_id=session_id,
            event_type=event_type,
            timestamp=parse_timestamp(timestamp),
            created_at=parse_timestamp(created_at),
            **kwargs,
        )

    @property
    def prompt_hash(self) -> str | None:
        return compute_prompt_hash(self.prompt_text)

    def with_sanitized_values(
        self,
        *,
        prompt_text: str | None,
        assistant_response_summary: str | None,
        tool_input_summary: str | None,
        tool_result_summary: str | None,
        metadata: dict[str, Any],
        raw_payload: Any,
        commands_executed: list[str],
    ) -> "CopilotEvent":
        return replace(
            self,
            prompt_text=prompt_text,
            assistant_response_summary=assistant_response_summary,
            tool_input_summary=tool_input_summary,
            tool_result_summary=tool_result_summary,
            metadata=metadata,
            raw_payload=raw_payload,
            commands_executed=commands_executed,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "repository": self.repository,
            "branch": self.branch,
            "workspace": self.workspace,
            "user_prompt_id": self.user_prompt_id,
            "parent_user_prompt_id": self.parent_user_prompt_id,
            "tool_name": self.tool_name,
            "prompt_text": self.prompt_text,
            "assistant_response_summary": self.assistant_response_summary,
            "tool_input_summary": self.tool_input_summary,
            "tool_result_summary": self.tool_result_summary,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "files_touched": list(self.files_touched),
            "commands_executed": list(self.commands_executed),
            "metadata": dict(self.metadata),
            "raw_payload": self.raw_payload,
            "created_at": self.created_at.isoformat(),
        }
