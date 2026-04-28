from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import typer

from .config import AppConfig, load_config, load_session_index, save_session_index
from .git_context import GitContext, collect_git_context
from .offline_queue import DEFAULT_PROCESS_LIMIT, OfflineQueue
from .sanitizer import sanitize_value
from .schema import ACTOR_PATHS, PROMPT_PATHS, SESSION_ID_PATHS, SUPPORTED_EVENTS, EventRecord, first_value, maybe_parse_json
from .storage_http import HttpEventSender, HttpSendResult, check_connectivity
from .storage_jsonl import JsonlEventWriter
from .storage_sqlite import SQLiteEventWriter

app = typer.Typer(help="Capture GitHub Copilot hook payloads to local storage and optional HTTP.")


def _read_stdin_payload() -> tuple[Any | None, dict[str, Any]]:
    metadata: dict[str, Any] = {"stdin_present": False, "stdin_mode": "tty"}
    if sys.stdin.isatty():
        return None, metadata

    raw_input = sys.stdin.read()
    if raw_input is None or not raw_input.strip():
        metadata["stdin_mode"] = "empty"
        return None, metadata

    metadata["stdin_present"] = True
    try:
        payload = json.loads(raw_input)
        metadata["stdin_mode"] = "json"
        return payload, metadata
    except json.JSONDecodeError as exc:
        metadata["stdin_mode"] = "raw_text"
        metadata["stdin_parse_error"] = str(exc)
        return {"_raw_stdin": raw_input}, metadata


def _ensure_storage_ready(config: AppConfig) -> None:
    try:
        config.ensure_home()
    except OSError as exc:
        typer.echo(
            (
                "Unable to initialize storage under "
                f"'{config.home_dir}'. Set COPILOT_SESSION_LOGGER_HOME "
                "to a writable directory and retry."
            ),
            err=True,
        )
        raise typer.Exit(code=1) from exc


def _is_effectively_writable(path: Path) -> bool:
    target = path if path.exists() else path.parent
    return target.exists() and os.access(target, os.W_OK)


def _local_write_check(config: AppConfig) -> tuple[bool, str | None]:
    try:
        config.ensure_home()
        probe_path = config.home_dir / ".doctor-write-test"
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink(missing_ok=True)
    except OSError as exc:
        return False, str(exc)
    return True, None


def _json_arg_to_mapping(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON for --metadata-json: {exc}") from exc
    if not isinstance(parsed, dict):
        raise typer.BadParameter("--metadata-json must decode to a JSON object.")
    return parsed


def _resolve_actor(payload: Any, actor_override: str | None, config: AppConfig) -> str | None:
    return (
        actor_override
        or first_value(payload, ACTOR_PATHS)
        or config.actor
    )


def _resolve_working_directory(payload: Any) -> str:
    payload_cwd = first_value(payload, (("cwd",), ("workingDirectory",), ("working_directory",)))
    if payload_cwd:
        return str(payload_cwd)
    return str(Path.cwd())


def _extract_user_prompt(payload: Any) -> str | None:
    return _stringify(first_value(payload, PROMPT_PATHS))


def _extract_tool_name(payload: Any, tool_name_override: str | None) -> str | None:
    return tool_name_override or _stringify(
        first_value(payload, (("toolName",), ("tool",), ("payload", "toolName")))
    )


def _extract_tool_args(payload: Any) -> Any:
    return maybe_parse_json(first_value(payload, (("toolArgs",), ("payload", "toolArgs"), ("request", "toolArgs"))))


def _extract_command(payload: Any, command_override: str | None) -> str | None:
    if command_override:
        return command_override

    tool_args = _extract_tool_args(payload)
    if isinstance(tool_args, dict):
        for key in ("command", "cmd", "script", "path"):
            if tool_args.get(key):
                return _stringify(tool_args[key])
        return json.dumps(tool_args, ensure_ascii=True, sort_keys=True)

    direct_value = first_value(payload, (("command",), ("payload", "command")))
    return _stringify(direct_value)


def _extract_status(payload: Any, status_override: str | None) -> str | None:
    if status_override:
        return status_override

    tool_result = maybe_parse_json(first_value(payload, (("toolResult",), ("payload", "toolResult"))))
    if isinstance(tool_result, dict):
        for key in ("resultType", "status", "outcome"):
            if tool_result.get(key):
                return _stringify(tool_result[key])
        if "success" in tool_result:
            return "success" if tool_result["success"] else "failure"

    value = first_value(payload, (("status",), ("reason",)))
    return _stringify(value)


def _extract_error(payload: Any, error_override: str | None) -> str | None:
    if error_override:
        return error_override

    error_value = maybe_parse_json(first_value(payload, (("error",), ("payload", "error"))))
    if isinstance(error_value, dict):
        message = error_value.get("message") or error_value.get("name")
        if message and error_value.get("name") and message != error_value["name"]:
            return f"{error_value['name']}: {message}"
        return _stringify(message)

    tool_result = maybe_parse_json(first_value(payload, (("toolResult",),)))
    if isinstance(tool_result, dict) and tool_result.get("resultType") == "failure":
        return _stringify(
            tool_result.get("textResultForLlm")
            or tool_result.get("error")
            or tool_result.get("message")
        )

    return _stringify(error_value)


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)


def _build_session_scope_key(repo_path: str | None, working_directory: str | None, actor: str | None) -> str:
    location = repo_path or working_directory or "unknown"
    return f"{actor or 'unknown'}::{Path(location).expanduser().resolve()}"


def _resolve_session_id(
    *,
    event_type: str,
    payload: Any,
    session_id_override: str | None,
    config: AppConfig,
    working_directory: str | None,
    repo_path: str | None,
    actor: str | None,
    persist_state: bool,
) -> tuple[str, str]:
    explicit_session_id = (
        session_id_override
        or _stringify(first_value(payload, SESSION_ID_PATHS))
    )
    scope_key = _build_session_scope_key(repo_path, working_directory, actor)
    sessions = load_session_index(config.session_state_path)

    if explicit_session_id:
        session_id = explicit_session_id
        strategy = "payload_or_arg"
    elif event_type == "sessionStart":
        session_id = str(uuid4())
        strategy = "generated_on_session_start"
    elif scope_key in sessions:
        session_id = sessions[scope_key]["session_id"]
        strategy = "session_cache_hit"
    else:
        session_id = str(uuid4())
        strategy = "generated_fallback"

    if persist_state:
        if event_type == "sessionEnd":
            sessions.pop(scope_key, None)
        else:
            sessions[scope_key] = {
                "session_id": session_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        save_session_index(config.session_state_path, sessions)

    return session_id, strategy


def _build_metadata(
    *,
    payload: Any,
    stdin_metadata: dict[str, Any],
    git_context: GitContext,
    session_strategy: str,
    metadata_override: dict[str, Any],
    config: AppConfig,
) -> dict[str, Any]:
    payload_dict = payload if isinstance(payload, dict) else {}
    metadata: dict[str, Any] = {
        "stdin": stdin_metadata,
        "session_strategy": session_strategy,
        "git": {
            "git_available": git_context.git_available,
            "is_repo": git_context.is_repo,
            "error": git_context.error,
        },
        "config_path": str(config.config_path) if config.config_path else None,
    }

    for key in ("source", "reason", "finalMessage"):
        if payload_dict.get(key) not in (None, ""):
            metadata[key] = payload_dict[key]

    tool_args = _extract_tool_args(payload)
    if tool_args is not None:
        metadata["tool_args"] = tool_args

    tool_result = maybe_parse_json(first_value(payload, (("toolResult",),)))
    if tool_result is not None:
        metadata["tool_result"] = tool_result

    if metadata_override:
        metadata.update(metadata_override)

    return metadata


def build_event_record(
    *,
    event_type: str,
    payload: Any,
    config: AppConfig,
    session_id_override: str | None = None,
    actor_override: str | None = None,
    tool_name_override: str | None = None,
    command_override: str | None = None,
    status_override: str | None = None,
    error_override: str | None = None,
    metadata_override: dict[str, Any] | None = None,
    stdin_metadata: dict[str, Any] | None = None,
    persist_session_state: bool = True,
) -> EventRecord:
    working_directory = _resolve_working_directory(payload)
    git_context = collect_git_context(working_directory)
    repo_path = git_context.repo_path or working_directory
    actor = _resolve_actor(payload, actor_override, config)
    session_id, session_strategy = _resolve_session_id(
        event_type=event_type,
        payload=payload,
        session_id_override=session_id_override,
        config=config,
        working_directory=working_directory,
        repo_path=repo_path,
        actor=actor,
        persist_state=persist_session_state,
    )

    metadata = _build_metadata(
        payload=payload,
        stdin_metadata=stdin_metadata or {"stdin_present": False, "stdin_mode": "unknown"},
        git_context=git_context,
        session_strategy=session_strategy,
        metadata_override=metadata_override or {},
        config=config,
    )
    user_prompt = _extract_user_prompt(payload)
    tool_name = _extract_tool_name(payload, tool_name_override)
    command = _extract_command(payload, command_override)
    status = _extract_status(payload, status_override)
    error = _extract_error(payload, error_override)

    if config.redact_secrets:
        user_prompt = sanitize_value(user_prompt)
        tool_name = sanitize_value(tool_name)
        command = sanitize_value(command)
        status = sanitize_value(status)
        error = sanitize_value(error)
        actor = sanitize_value(actor)
        sanitized_payload = sanitize_value(payload)
        sanitized_metadata = sanitize_value(metadata)
    else:
        sanitized_payload = payload
        sanitized_metadata = metadata

    return EventRecord(
        session_id=session_id,
        event_type=event_type,
        timestamp=first_value(payload, (("timestamp",),)) if payload is not None else None,
        user_prompt=user_prompt,
        repo_path=git_context.repo_path or working_directory,
        repo_name=git_context.repo_name or Path(working_directory).name,
        git_branch=git_context.git_branch,
        git_commit=git_context.git_commit,
        working_directory=working_directory,
        actor=actor,
        files_changed=git_context.files_changed,
        tool_name=tool_name,
        command=command,
        status=status,
        error=error,
        raw_payload=sanitized_payload,
        metadata=sanitized_metadata,
    )


def persist_event(record: EventRecord, config: AppConfig, sqlite_enabled_override: bool | None = None) -> dict[str, str]:
    outputs: dict[str, str] = {}
    if config.storage.jsonl_enabled:
        jsonl_path = JsonlEventWriter(config.logs_dir).write(record)
        outputs["jsonl"] = str(jsonl_path)

    sqlite_enabled = config.storage.sqlite_enabled if sqlite_enabled_override is None else sqlite_enabled_override
    if sqlite_enabled:
        sqlite_path = SQLiteEventWriter(config.sqlite_path).write(record)
        outputs["sqlite"] = str(sqlite_path)

    return outputs


def _format_http_error(result: HttpSendResult) -> str | None:
    if result.status_code is not None:
        return f"{result.error or 'http_error'}:{result.status_code}"
    return result.error


def flush_offline_queue(config: AppConfig, *, max_items: int = DEFAULT_PROCESS_LIMIT) -> dict[str, Any]:
    if not config.http.enabled:
        return {
            "http_enabled": False,
            "flushed": False,
            "reason": "http_disabled",
        }
    if not config.http.endpoint:
        return {
            "http_enabled": True,
            "flushed": False,
            "reason": "endpoint_not_configured",
        }
    if not config.http.api_key:
        return {
            "http_enabled": True,
            "flushed": False,
            "reason": "api_key_not_configured",
        }
    if not config.http.offline_queue_enabled:
        return {
            "http_enabled": True,
            "flushed": False,
            "reason": "offline_queue_disabled",
        }

    queue = OfflineQueue(config.http.queue_dir, max_retries=config.http.max_retries)
    summary = queue.process_pending(
        HttpEventSender(config.http),
        max_items=max_items,
    )
    return {
        "http_enabled": True,
        "flushed": True,
        "queue_dir": str(config.http.queue_dir),
        "summary": summary.to_jsonable(),
    }


def deliver_event_http(
    record: EventRecord,
    config: AppConfig,
    *,
    replay_pending: bool = True,
    replay_limit: int = 1,
) -> dict[str, Any]:
    if not config.http.enabled:
        return {"enabled": False}

    delivery: dict[str, Any] = {"enabled": True}
    sender = HttpEventSender(config.http)

    if config.http.offline_queue_enabled and replay_pending:
        delivery["offline_flush"] = flush_offline_queue(config, max_items=replay_limit)

    result = sender.send_event(record)
    delivery["send"] = result.to_jsonable()

    if result.success or not config.http.offline_queue_enabled:
        return delivery

    if result.error in {"endpoint_not_configured", "api_key_not_configured"}:
        delivery["queue_action"] = "skipped_configuration_error"
        return delivery

    queue = OfflineQueue(config.http.queue_dir, max_retries=config.http.max_retries)
    last_error = _format_http_error(result)
    if result.retryable:
        queue.enqueue(record, retry_count=1, last_error=last_error)
        delivery["queue_action"] = "pending"
    else:
        queue.dead_letter(record, retry_count=0, last_error=last_error)
        delivery["queue_action"] = "dead_letter"
    return delivery


@app.command()
def log(
    event: str = typer.Option(..., "--event", help="Copilot hook event type."),
    session_id: str | None = typer.Option(None, "--session-id", help="Override session ID."),
    actor: str | None = typer.Option(None, "--actor", help="Override actor/user."),
    tool_name: str | None = typer.Option(None, "--tool-name", help="Override tool name."),
    command: str | None = typer.Option(None, "--command", help="Override captured command."),
    status: str | None = typer.Option(None, "--status", help="Override status value."),
    error: str | None = typer.Option(None, "--error", help="Override error message."),
    metadata_json: str | None = typer.Option(None, "--metadata-json", help="Additional metadata as JSON object."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the event record instead of persisting it."),
    config_file: Path | None = typer.Option(None, "--config", exists=False, dir_okay=False, resolve_path=True, help="Path to a YAML config file."),
    sqlite_enabled: bool | None = typer.Option(None, "--sqlite/--no-sqlite", help="Enable or disable SQLite for this invocation."),
) -> None:
    if event not in SUPPORTED_EVENTS:
        raise typer.BadParameter(
            f"Unsupported --event '{event}'. Expected one of: {', '.join(SUPPORTED_EVENTS)}."
        )

    config = load_config(config_file)
    should_persist = not (dry_run or config.dry_run)
    if should_persist:
        _ensure_storage_ready(config)

    payload, stdin_metadata = _read_stdin_payload()
    metadata_override = _json_arg_to_mapping(metadata_json)
    record = build_event_record(
        event_type=event,
        payload=payload,
        config=config,
        session_id_override=session_id,
        actor_override=actor,
        tool_name_override=tool_name,
        command_override=command,
        status_override=status,
        error_override=error,
        metadata_override=metadata_override,
        stdin_metadata=stdin_metadata,
        persist_session_state=should_persist,
    )

    if not should_persist:
        typer.echo(json.dumps(record.to_jsonable(), ensure_ascii=True, indent=2))
        return

    if sqlite_enabled is not None:
        config.storage.sqlite_enabled = sqlite_enabled
    persist_event(record, config)
    deliver_event_http(record, config)


@app.command()
def flush(
    max_items: int = typer.Option(DEFAULT_PROCESS_LIMIT, "--max-items", min=1, max=DEFAULT_PROCESS_LIMIT, help="Maximum queued events to retry."),
    config_file: Path | None = typer.Option(None, "--config", exists=False, dir_okay=False, resolve_path=True, help="Path to a YAML config file."),
) -> None:
    config = load_config(config_file)
    _ensure_storage_ready(config)
    report = flush_offline_queue(config, max_items=max_items)
    typer.echo(json.dumps(report, ensure_ascii=True, indent=2))
    if not report.get("flushed"):
        raise typer.Exit(code=1)


@app.command()
def doctor(
    config_file: Path | None = typer.Option(None, "--config", exists=False, dir_okay=False, resolve_path=True, help="Path to a YAML config file."),
    check_http: bool = typer.Option(False, "--check-http", help="Attempt a basic connectivity check to the configured endpoint."),
) -> None:
    config = load_config(config_file)
    git_context = collect_git_context(Path.cwd())
    writable, write_error = _local_write_check(config)
    connectivity = None
    if check_http and config.http.endpoint:
        connectivity = check_connectivity(
            config.http.endpoint,
            timeout_seconds=config.http.timeout_seconds,
            api_key=config.http.api_key,
        ).to_jsonable()
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "home_dir": str(config.home_dir),
        "logs_dir": str(config.logs_dir),
        "sqlite_enabled": config.storage.sqlite_enabled,
        "sqlite_path": str(config.sqlite_path),
        "config_path": str(config.config_path) if config.config_path else None,
        "session_state_path": str(config.session_state_path),
        "http": {
            "enabled": config.http.enabled,
            "endpoint": config.http.endpoint,
            "endpoint_configured": bool(config.http.endpoint),
            "api_key_present": bool(config.http.api_key),
            "timeout_seconds": config.http.timeout_seconds,
            "offline_queue_enabled": config.http.offline_queue_enabled,
            "max_retries": config.http.max_retries,
            "queue_dir": str(config.http.queue_dir),
            "connectivity": connectivity if connectivity is not None else "not_checked",
        },
        "writable": {
            "home_dir": _is_effectively_writable(config.home_dir),
            "logs_dir": _is_effectively_writable(config.logs_dir),
            "sqlite_path_parent": _is_effectively_writable(config.sqlite_path.parent),
            "session_state_parent": _is_effectively_writable(config.session_state_path.parent),
            "queue_dir": _is_effectively_writable(config.http.queue_dir),
            "write_probe": writable,
            "write_error": write_error,
        },
        "git": {
            "git_available": git_context.git_available,
            "is_repo": git_context.is_repo,
            "repo_path": git_context.repo_path,
            "repo_name": git_context.repo_name,
            "git_branch": git_context.git_branch,
            "git_commit": git_context.git_commit,
            "files_changed": git_context.files_changed,
            "error": git_context.error,
        },
    }
    typer.echo(json.dumps(report, ensure_ascii=True, indent=2))


@app.command()
def demo(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print demo events instead of persisting them."),
    send_http: bool = typer.Option(False, "--send-http", help="Send demo events to the configured HTTP endpoint."),
    config_file: Path | None = typer.Option(None, "--config", exists=False, dir_okay=False, resolve_path=True, help="Path to a YAML config file."),
    sqlite_enabled: bool | None = typer.Option(None, "--sqlite/--no-sqlite", help="Enable or disable SQLite for demo output."),
) -> None:
    config = load_config(config_file)
    should_persist = not (dry_run or config.dry_run)
    if should_persist:
        _ensure_storage_ready(config)

    session_id = str(uuid4())
    payloads = [
        (
            "sessionStart",
            {
                "timestamp": 1704614400000,
                "cwd": str(Path.cwd()),
                "source": "new",
                "initialPrompt": "Create a safe logger for Copilot prompts",
                "sessionId": session_id,
            },
        ),
        (
            "userPromptSubmitted",
            {
                "timestamp": 1704614460000,
                "cwd": str(Path.cwd()),
                "prompt": "Explain this repository and add observability hooks",
                "sessionId": session_id,
                "actor": config.actor or "demo-user",
            },
        ),
        (
            "postToolUse",
            {
                "timestamp": 1704614520000,
                "cwd": str(Path.cwd()),
                "toolName": "powershell",
                "toolArgs": json.dumps({"command": "Get-ChildItem", "description": "List files"}),
                "toolResult": {
                    "resultType": "success",
                    "output": "README.md\nsrc\nexamples",
                },
                "sessionId": session_id,
            },
        ),
    ]

    records = [
        build_event_record(
            event_type=event_type,
            payload=payload,
            config=config,
            stdin_metadata={"stdin_present": True, "stdin_mode": "demo"},
            persist_session_state=should_persist,
        )
        for event_type, payload in payloads
    ]

    if not should_persist:
        typer.echo(json.dumps([record.to_jsonable() for record in records], ensure_ascii=True, indent=2))
        return

    if sqlite_enabled is not None:
        config.storage.sqlite_enabled = sqlite_enabled
    if send_http:
        config.http.enabled = True

    outputs = [persist_event(record, config) for record in records]
    deliveries = []
    if send_http:
        deliveries = [
            deliver_event_http(record, config, replay_pending=index == 0)
            for index, record in enumerate(records)
        ]
    typer.echo(
        json.dumps(
            {
                "events_written": len(records),
                "outputs": outputs,
                "http": deliveries,
            },
            ensure_ascii=True,
            indent=2,
        )
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
