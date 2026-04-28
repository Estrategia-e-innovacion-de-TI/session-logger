from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .auth import require_api_key
from .config import BackendConfig, load_config
from .sanitizer import sanitize_value
from .schema import BatchRequest, EventRecord, validate_event_type_allowed
from .storage.jsonl import JsonlEventStorage
from .storage.sqlite import SQLiteEventStorage

logger = logging.getLogger("copilot_log_backend")

app = FastAPI(title="Copilot Log Backend", version="0.1.0")


@app.middleware("http")
async def reject_large_bodies(request: Request, call_next):
    config = load_config()
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            body_size = int(content_length)
        except ValueError:
            body_size = 0
        if body_size > config.max_body_bytes:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "Request body too large"},
            )
    return await call_next(request)


def _storage(config: BackendConfig):
    config.ensure_home()
    if config.storage == "sqlite":
        return SQLiteEventStorage(config.sqlite_path)
    return JsonlEventStorage(config.events_dir)


def _sanitize_record(record: EventRecord) -> dict[str, Any]:
    sanitized = sanitize_value(record.to_jsonable())
    if not isinstance(sanitized, dict):
        raise HTTPException(status_code=400, detail="Invalid event payload")
    return EventRecord.model_validate(sanitized).to_jsonable()


def _accept_event(record: EventRecord, config: BackendConfig) -> dict[str, Any]:
    try:
        validate_event_type_allowed(
            record.event_type,
            allow_unknown=config.allow_unknown_event_types,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    event = _sanitize_record(record)
    _storage(config).write_event(event)
    logger.info(
        "event_ingested event_id=%s event_type=%s actor=%s repo_name=%s status=accepted",
        event.get("event_id"),
        event.get("event_type"),
        event.get("actor"),
        event.get("repo_name"),
    )
    return event


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/events", status_code=status.HTTP_202_ACCEPTED)
def ingest_event(
    record: EventRecord,
    config: BackendConfig = Depends(require_api_key),
) -> dict[str, str]:
    event = _accept_event(record, config)
    return {"status": "accepted", "event_id": str(event["event_id"])}


@app.post("/v1/events/batch")
def ingest_batch(
    batch: BatchRequest,
    config: BackendConfig = Depends(require_api_key),
) -> dict[str, Any]:
    accepted: list[str] = []
    rejected: list[dict[str, Any]] = []

    for index, raw_event in enumerate(batch.events):
        try:
            record = EventRecord.model_validate(raw_event)
            event = _accept_event(record, config)
        except (ValidationError, HTTPException) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else exc.errors()
            rejected.append({"index": index, "detail": detail})
            continue
        accepted.append(str(event["event_id"]))

    return {
        "accepted": len(accepted),
        "rejected": len(rejected),
        "accepted_event_ids": accepted,
        "rejections": rejected,
    }


@app.get("/v1/events")
def query_events(
    config: BackendConfig = Depends(require_api_key),
    session_id: str | None = None,
    event_type: str | None = None,
    repo_name: str | None = None,
    actor: str | None = None,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    events = _storage(config).query_events(
        session_id=session_id,
        event_type=event_type,
        repo_name=repo_name,
        actor=actor,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
        limit=limit,
    )
    return {"events": events, "count": len(events)}
