"""Load and normalize session-logger and Copilot trace files.

The loader intentionally does not import the session-logger product package.
It accepts the OTLP-like JSON exported by the current examples and simpler
event arrays used by tests or future experiments.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable


@dataclass
class NormalizedEvent:
    """Common event representation used by the PoC."""

    session_id: str | None
    event_type: str | None
    timestamp: str | None
    repository: str | None
    branch: str | None
    git_commit: str | None
    userPrompt_id: str | None
    parent_userPrompt_id: str | None
    prompt_text: str | None
    assistant_response: str | None
    tool_name: str | None
    tool_input_summary: str | None
    tool_result_summary: str | None
    files_touched: list[str]
    commands_executed: list[str]
    raw_event: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_traces(paths: Iterable[str | Path]) -> list[NormalizedEvent]:
    """Read one or more JSON traces and return normalized events."""

    events: list[NormalizedEvent] = []
    for path in paths:
        trace_path = Path(path)
        payload = json.loads(trace_path.read_text(encoding="utf-8-sig"))
        events.extend(_normalize_payload(payload))
    return events


def _normalize_payload(payload: Any) -> list[NormalizedEvent]:
    if isinstance(payload, list):
        return [_normalize_plain_event(event) for event in payload if isinstance(event, dict)]

    if not isinstance(payload, dict):
        return []

    if "batches" in payload:
        return [_normalize_span(span) for span in _iter_otlp_spans(payload)]

    if isinstance(payload.get("events"), list):
        return [_normalize_plain_event(event) for event in payload["events"] if isinstance(event, dict)]

    return [_normalize_plain_event(payload)]


def _iter_otlp_spans(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for batch in payload.get("batches", []):
        for library in batch.get("instrumentationLibrarySpans", []):
            for span in library.get("spans", []):
                if isinstance(span, dict):
                    yield span


def _normalize_span(span: dict[str, Any]) -> NormalizedEvent:
    attrs = _attributes_to_dict(span.get("attributes", []))
    metadata = _json_object(attrs.get("metadata"))
    raw_payload = _json_object(attrs.get("raw_payload"))
    tool_args = _json_object(attrs.get("gen_ai.tool.call.arguments"))
    hook_input = _json_object(attrs.get("copilot_chat.hook_input"))

    files = _unique(
        _parse_list(attrs.get("files_touched"))
        + _parse_list(attrs.get("files_added"))
        + _extract_paths(tool_args)
        + _extract_paths(hook_input)
        + _list_from_value(attrs.get("github.copilot.tool.parameters.file_path"))
    )
    commands = _unique(
        _parse_list(attrs.get("commands_executed"))
        + _list_from_value(_nested_get(hook_input, ["tool_input", "command"]))
        + _list_from_value(attrs.get("copilot_chat.hook_command"))
    )

    prompt_text = _first_text(
        attrs.get("prompt_text"),
        attrs.get("copilot_chat.user_request"),
        _extract_message_text(attrs.get("gen_ai.input.messages"), role="user"),
        raw_payload.get("prompt") if isinstance(raw_payload, dict) else None,
    )
    assistant_response = _first_text(
        attrs.get("assistant_response"),
        attrs.get("assistant_response_summary"),
        _extract_message_text(attrs.get("gen_ai.output.messages"), role="assistant"),
        attrs.get("gen_ai.tool.call.arguments"),
    )

    git_meta = metadata.get("git", {}) if isinstance(metadata, dict) else {}
    session_id = _first_text(
        attrs.get("session_id"),
        attrs.get("copilot_chat.session_id"),
        attrs.get("copilot_chat.chat_session_id"),
        attrs.get("gen_ai.conversation.id"),
        raw_payload.get("session_id") if isinstance(raw_payload, dict) else None,
    )

    return NormalizedEvent(
        session_id=session_id,
        event_type=_first_text(attrs.get("event_type"), span.get("name"), attrs.get("gen_ai.operation.name")),
        timestamp=_first_text(attrs.get("timestamp"), attrs.get("created_at"), _nano_to_iso(span.get("startTimeUnixNano"))),
        repository=_first_text(
            attrs.get("repository"),
            attrs.get("github.copilot.git.repository"),
            attrs.get("copilot_chat.repo.remote_url"),
            git_meta.get("repo_name") if isinstance(git_meta, dict) else None,
        ),
        branch=_first_text(
            attrs.get("branch"),
            attrs.get("github.copilot.git.branch"),
            attrs.get("copilot_chat.repo.head_branch_name"),
            git_meta.get("git_branch") if isinstance(git_meta, dict) else None,
        ),
        git_commit=_first_text(
            attrs.get("git_commit"),
            attrs.get("github.copilot.git.commit_sha"),
            attrs.get("copilot_chat.repo.head_commit_hash"),
            git_meta.get("git_commit") if isinstance(git_meta, dict) else None,
        ),
        userPrompt_id=_first_text(attrs.get("userPrompt_id"), attrs.get("gen_ai.conversation.id")),
        parent_userPrompt_id=_none_if_null(attrs.get("parent_userPrompt_id")),
        prompt_text=prompt_text,
        assistant_response=assistant_response,
        tool_name=_first_text(
            attrs.get("tool_name"),
            attrs.get("toolName"),
            attrs.get("gen_ai.tool.name"),
            _nested_get(hook_input, ["tool_name"]),
        ),
        tool_input_summary=_first_text(
            attrs.get("tool_input_summary"),
            attrs.get("gen_ai.tool.call.arguments"),
            attrs.get("copilot_chat.hook_input"),
        ),
        tool_result_summary=_first_text(attrs.get("tool_result_summary"), attrs.get("gen_ai.tool.call.result")),
        files_touched=files,
        commands_executed=commands,
        raw_event={"span": span, "attributes": attrs},
    )


def _normalize_plain_event(event: dict[str, Any]) -> NormalizedEvent:
    metadata = _json_object(event.get("metadata"))
    git_meta = metadata.get("git", {}) if isinstance(metadata, dict) else {}
    tool_args = event.get("toolArgs") or event.get("tool_input") or event.get("toolInput") or {}
    tool_result = event.get("toolResult") or event.get("tool_result") or {}

    files = _unique(
        _parse_list(event.get("files_touched"))
        + _parse_list(event.get("filesTouched"))
        + _parse_list(event.get("files_added"))
        + _extract_paths(event)
        + _extract_paths(tool_args)
        + _extract_paths(tool_result)
    )
    commands = _unique(
        _parse_list(event.get("commands_executed"))
        + _list_from_value(event.get("command"))
        + _list_from_value(tool_args.get("command") if isinstance(tool_args, dict) else None)
    )

    return NormalizedEvent(
        session_id=_first_text(event.get("session_id"), event.get("sessionId")),
        event_type=_first_text(event.get("event_type"), event.get("eventType"), event.get("hook_event_name")),
        timestamp=_first_text(event.get("timestamp"), event.get("created_at")),
        repository=_first_text(event.get("repository"), git_meta.get("repo_name") if isinstance(git_meta, dict) else None),
        branch=_first_text(event.get("branch"), git_meta.get("git_branch") if isinstance(git_meta, dict) else None),
        git_commit=_first_text(event.get("git_commit"), git_meta.get("git_commit") if isinstance(git_meta, dict) else None),
        userPrompt_id=_first_text(event.get("userPrompt_id"), event.get("userPromptId")),
        parent_userPrompt_id=_first_text(event.get("parent_userPrompt_id"), event.get("parentUserPromptId")),
        prompt_text=_first_text(event.get("prompt_text"), event.get("prompt"), event.get("user_request")),
        assistant_response=_first_text(event.get("assistant_response"), event.get("assistantResponse")),
        tool_name=_first_text(event.get("tool_name"), event.get("toolName")),
        tool_input_summary=_stringify(tool_args),
        tool_result_summary=_stringify(tool_result),
        files_touched=files,
        commands_executed=commands,
        raw_event=event,
    )


def _attributes_to_dict(attributes: list[dict[str, Any]]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for attr in attributes or []:
        key = attr.get("key")
        if not key:
            continue
        flattened[key] = _otel_value(attr.get("value", {}))
    return flattened


def _otel_value(value: dict[str, Any]) -> Any:
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in value:
            return value[key]
    if "arrayValue" in value:
        return [_otel_value(item) for item in value.get("arrayValue", {}).get("values", [])]
    if "kvlistValue" in value:
        return {
            item.get("key"): _otel_value(item.get("value", {}))
            for item in value.get("kvlistValue", {}).get("values", [])
            if item.get("key")
        }
    return None


def _extract_message_text(value: Any, role: str | None = None) -> str | None:
    messages = _json_object(value)
    if not isinstance(messages, list):
        return None
    parts_out: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        if role and message.get("role") != role:
            continue
        for part in message.get("parts", []):
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and part.get("content"):
                parts_out.append(str(part["content"]))
            elif part.get("type") == "tool_call":
                name = part.get("name", "tool_call")
                arguments = part.get("arguments", "")
                parts_out.append(f"{name}: {arguments}")
    return "\n".join(parts_out) if parts_out else None


def _extract_paths(value: Any) -> list[str]:
    paths: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                lowered = str(key).lower()
                if lowered in {
                    "filepath",
                    "file_path",
                    "path",
                    "file",
                    "filename",
                    "fsPath".lower(),
                }:
                    paths.extend(_list_from_value(item))
                elif lowered in {"paths", "files", "attachments", "images", "files_added", "files_touched"}:
                    paths.extend(_parse_list(item))
                walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(_json_object(value))
    return [path for path in paths if _looks_like_file_path(path)]


def _parse_list(value: Any) -> list[str]:
    parsed = _json_object(value)
    if isinstance(parsed, list):
        result: list[str] = []
        for item in parsed:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                result.extend(_extract_paths(item))
        return result
    return _list_from_value(parsed)


def _json_object(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped == "null":
        return None
    if stripped[0:1] not in {"{", "["}:
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _list_from_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, str):
        if not value or value == "null":
            return []
        return [value]
    return [str(value)]


def _first_text(*values: Any) -> str | None:
    for value in values:
        value = _none_if_null(value)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            text = _stringify(value)
        else:
            text = str(value)
        if text:
            return text
    return None


def _none_if_null(value: Any) -> Any:
    if value in (None, "", "null"):
        return None
    return value


def _nested_get(value: Any, path: list[str]) -> Any:
    node = _json_object(value)
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _stringify(value: Any) -> str | None:
    value = _none_if_null(value)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _looks_like_file_path(value: str) -> bool:
    text = str(value).strip()
    if not text:
        return False
    name = text.replace("\\", "/").rstrip("/").split("/")[-1]
    if name in {"Dockerfile", "Makefile", "requirements.txt", "pyproject.toml"}:
        return True
    if "." not in name:
        return False
    return True


def _nano_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        seconds = int(value) / 1_000_000_000
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Normalize trace JSON files.")
    parser.add_argument("trace_files", nargs="+")
    args = parser.parse_args()
    for event in load_traces(args.trace_files):
        print(json.dumps(event.to_dict(), ensure_ascii=False))
