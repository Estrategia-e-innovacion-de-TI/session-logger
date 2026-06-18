"""Extract AI contribution evidence from normalized trace events."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any, Iterable

try:
    from trace_loader import NormalizedEvent
except ImportError:  # pragma: no cover - package-style fallback
    from .trace_loader import NormalizedEvent


CODE_REQUEST_RE = re.compile(
    r"\b(genera|generar|regenera|crear|crea|modifica|modificar|implementar|implementa|codigo|code|function|class|diff|snippet)\b",
    re.IGNORECASE,
)
NO_CODE_RE = re.compile(r"\b(no generes codigo|no propongas diff|solo responde en texto|no snippets)\b", re.IGNORECASE)
CODE_FENCE_RE = re.compile(r"```(?:[\w+-]+)?\s*(.*?)```", re.DOTALL)
CODE_LINE_RE = re.compile(r"^\s*(def |class |import |from |if __name__|return |raise |for |while )", re.MULTILINE)
EDIT_TOOLS = {"create_file", "replace_string_in_file", "insert_edit_into_file", "apply_patch", "edit_file", "write_file"}


@dataclass
class AIEvidence:
    """Evidence item used by the scorer."""

    session_id: str | None
    evidence_type: str
    source_event_type: str | None
    timestamp: str | None
    repository: str | None
    branch: str | None
    git_commit: str | None
    files: list[str]
    snippets: list[str]
    commands: list[str]
    score_hint: float
    direct: bool
    description: str
    raw_event: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_evidence(events: Iterable[NormalizedEvent | dict[str, Any]]) -> list[AIEvidence]:
    """Classify trace events into direct, approximate, and indirect evidence."""

    evidence: list[AIEvidence] = []
    for event_like in events:
        event = _coerce_event(event_like)
        evidence.extend(_event_evidence(event))

    return evidence


def _event_evidence(event: NormalizedEvent) -> list[AIEvidence]:
    evidence: list[AIEvidence] = []
    prompt = event.prompt_text or ""
    assistant_response = event.assistant_response or ""
    tool_input = event.tool_input_summary or ""
    tool_result = event.tool_result_summary or ""
    tool_name = (event.tool_name or "").strip()

    code_requested = bool(CODE_REQUEST_RE.search(_ascii_lower(prompt)))
    no_code = bool(NO_CODE_RE.search(_ascii_lower(prompt)))

    prompt_item = _prompt_evidence(event, prompt, code_requested, no_code)
    if prompt_item is not None:
        evidence.append(prompt_item)

    response_snippets = _response_snippets(event, assistant_response)
    if response_snippets:
        evidence.append(
            _item(
                event,
                "direct_code_evidence",
                response_snippets,
                [],
                0.90,
                True,
                "Assistant response contains code-like content.",
            )
        )

    tool_item = _tool_evidence(event, tool_name, tool_input)
    if tool_item is not None:
        evidence.append(tool_item)

    file_item = _file_touch_evidence(event, tool_name)
    if file_item is not None:
        evidence.append(file_item)

    if event.commands_executed:
        evidence.append(
            _item(
                event,
                "command_evidence",
                [],
                event.commands_executed,
                0.25,
                False,
                "Trace includes commands executed during the AI-assisted session.",
            )
        )

    if event.timestamp and (code_requested or event.files_touched or tool_name):
        evidence.append(
            _item(
                event,
                "temporal_evidence",
                [],
                [],
                0.20,
                False,
                "Timestamp can be compared with commit time for temporal proximity.",
            )
        )

    if tool_result and "successfully edited" in tool_result.lower():
        evidence.append(
            _item(
                event,
                "file_touch_evidence",
                [],
                [],
                0.70,
                True,
                "Tool result confirms a file was edited.",
            )
        )

    return evidence


def _prompt_evidence(event: NormalizedEvent, prompt: str, code_requested: bool, no_code: bool) -> AIEvidence | None:
    if not prompt:
        return None
    if code_requested and not no_code:
        return _item(
            event,
            "assistant_text_evidence",
            [prompt],
            [],
            0.45,
            False,
            "Prompt asks the assistant to generate or modify code.",
        )
    return _item(
        event,
        "weak_indirect_evidence",
        [],
        [],
        0.10,
        False,
        "Prompt is AI interaction evidence but does not request code generation directly.",
    )


def _response_snippets(event: NormalizedEvent, assistant_response: str) -> list[str]:
    snippets = _extract_code_snippets(assistant_response)
    snippets.extend(_extract_tool_snippets(assistant_response))
    snippets.extend(_extract_raw_tool_call_snippets(event))
    return [snippet for snippet in snippets if snippet]


def _tool_evidence(event: NormalizedEvent, tool_name: str, tool_input: str) -> AIEvidence | None:
    tool_snippets = _extract_tool_snippets(tool_input)
    if tool_name not in EDIT_TOOLS and not tool_snippets:
        return None
    return _item(
        event,
        "direct_code_evidence",
        tool_snippets,
        [],
        1.00,
        True,
        f"Tool call '{tool_name or 'unknown'}' is associated with file creation or editing.",
    )


def _file_touch_evidence(event: NormalizedEvent, tool_name: str) -> AIEvidence | None:
    if not event.files_touched:
        return None
    is_edit_tool = tool_name in EDIT_TOOLS
    return _item(
        event,
        "file_touch_evidence",
        [],
        [],
        0.55 if is_edit_tool else 0.35,
        is_edit_tool,
        "Trace references files touched or inspected during the AI session.",
    )


def collect_evidence_text(evidence: Iterable[AIEvidence]) -> list[str]:
    """Return snippets and prompt text useful for similarity comparison."""

    texts: list[str] = []
    for item in evidence:
        texts.extend(item.snippets)
        if item.evidence_type == "assistant_text_evidence":
            texts.extend(item.snippets)
    return [text for text in texts if text]


def summarize_evidence(evidence: Iterable[AIEvidence]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    files: set[str] = set()
    sessions: set[str] = set()
    for item in evidence:
        counts[item.evidence_type] = counts.get(item.evidence_type, 0) + 1
        files.update(item.files)
        if item.session_id:
            sessions.add(item.session_id)
    return {
        "total_evidence_items": sum(counts.values()),
        "evidence_by_type": counts,
        "files": sorted(files),
        "sessions": sorted(sessions),
    }


def _coerce_event(event_like: NormalizedEvent | dict[str, Any]) -> NormalizedEvent:
    if isinstance(event_like, NormalizedEvent):
        return event_like
    return NormalizedEvent(
        session_id=event_like.get("session_id"),
        event_type=event_like.get("event_type"),
        timestamp=event_like.get("timestamp"),
        repository=event_like.get("repository"),
        branch=event_like.get("branch"),
        git_commit=event_like.get("git_commit"),
        userPrompt_id=event_like.get("userPrompt_id"),
        parent_userPrompt_id=event_like.get("parent_userPrompt_id"),
        prompt_text=event_like.get("prompt_text"),
        assistant_response=event_like.get("assistant_response"),
        tool_name=event_like.get("tool_name"),
        tool_input_summary=event_like.get("tool_input_summary"),
        tool_result_summary=event_like.get("tool_result_summary"),
        files_touched=list(event_like.get("files_touched") or []),
        commands_executed=list(event_like.get("commands_executed") or []),
        raw_event=event_like.get("raw_event") or event_like,
    )


def _item(
    event: NormalizedEvent,
    evidence_type: str,
    snippets: list[str],
    commands: list[str],
    score_hint: float,
    direct: bool,
    description: str,
) -> AIEvidence:
    return AIEvidence(
        session_id=event.session_id,
        evidence_type=evidence_type,
        source_event_type=event.event_type,
        timestamp=event.timestamp,
        repository=event.repository,
        branch=event.branch,
        git_commit=event.git_commit,
        files=event.files_touched,
        snippets=snippets,
        commands=commands,
        score_hint=score_hint,
        direct=direct,
        description=description,
        raw_event=event.raw_event,
    )


def _extract_code_snippets(text: str) -> list[str]:
    snippets = [match.group(1).strip() for match in CODE_FENCE_RE.finditer(text or "") if match.group(1).strip()]
    if not snippets and CODE_LINE_RE.search(text or ""):
        snippets.append(text.strip())
    return snippets


def _extract_tool_snippets(text: str) -> list[str]:
    parsed = _json_object(text)
    if parsed is text and isinstance(text, str):
        parsed = _extract_embedded_tool_payloads(text)
    snippets = _collect_tool_snippets(parsed)
    if not snippets and isinstance(text, str):
        snippets.extend(_extract_string_field_values(text, ["newString", "content", "code", "replacement"]))
    if not snippets:
        snippets.extend(_extract_code_snippets(text))
    return [snippet for snippet in snippets if snippet]


def _extract_embedded_tool_payloads(text: str) -> Any:
    payloads: list[Any] = []
    for match in re.finditer(r"[A-Za-z_]\w*:\s*(\{[^}]*\}|\[[^\]]*\])", text or "", re.DOTALL):
        candidate = _json_object(match.group(1))
        if isinstance(candidate, (dict, list)):
            payloads.append(candidate)
    return payloads or text


def _extract_raw_tool_call_snippets(event: NormalizedEvent) -> list[str]:
    raw_event = event.raw_event or {}
    attributes = raw_event.get("attributes", {}) if isinstance(raw_event, dict) else {}
    messages = _json_object(attributes.get("gen_ai.output.messages"))
    if not isinstance(messages, list):
        return _extract_tool_snippets(str(attributes.get("gen_ai.output.messages", "")))

    snippets: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        for part in message.get("parts", []):
            if not isinstance(part, dict) or part.get("type") != "tool_call":
                continue
            snippets.extend(_extract_tool_snippets(part.get("arguments", "")))
    return snippets


def _extract_string_field_values(text: str, field_names: list[str]) -> list[str]:
    values: list[str] = []
    for field_name in field_names:
        values.extend(_extract_string_field_values_for_name(text, field_name))
    return values


def _collect_tool_snippets(node: Any) -> list[str]:
    snippets: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key) in {"newString", "content", "code", "replacement"} and isinstance(value, str):
                snippets.append(value)
            snippets.extend(_collect_tool_snippets(value))
    elif isinstance(node, list):
        for item in node:
            snippets.extend(_collect_tool_snippets(item))
    return snippets


def _extract_string_field_values_for_name(text: str, field_name: str) -> list[str]:
    values: list[str] = []
    token = f'"{field_name}":"'
    start = 0
    while True:
        index = text.find(token, start)
        if index == -1:
            return values
        raw_value, end_index = _read_json_string_value(text, index + len(token))
        values.append(_decode_json_string_value(raw_value))
        start = end_index


def _read_json_string_value(text: str, start_index: int) -> tuple[str, int]:
    cursor = start_index
    escaped = False
    buffer: list[str] = []
    while cursor < len(text):
        char = text[cursor]
        if escaped:
            buffer.append(char)
            escaped = False
        elif char == "\\":
            buffer.append(char)
            escaped = True
        elif char == '"':
            return "".join(buffer), cursor + 1
        else:
            buffer.append(char)
        cursor += 1
    return "".join(buffer), cursor


def _decode_json_string_value(raw_value: str) -> str:
    try:
        return json.loads(f'"{raw_value}"')
    except json.JSONDecodeError:
        return raw_value


def _json_object(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0:1] not in {"{", "["}:
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _ascii_lower(value: str) -> str:
    translation = str.maketrans("áéíóúÁÉÍÓÚñÑ", "aeiouAEIOUnN")
    return value.translate(translation).lower()
