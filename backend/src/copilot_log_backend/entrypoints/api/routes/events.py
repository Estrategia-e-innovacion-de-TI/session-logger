from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError

from copilot_log_backend.application.config import BackendConfig
from copilot_log_backend.application.container import ApplicationContainer
from copilot_log_backend.domain.exceptions import DomainError
from copilot_log_backend.usecases.ingest_event_batch import BatchIngestError, BatchIngestResult

from ..auth import require_api_key
from ..dependencies import get_container
from ..dto.event_request import BatchEventRequest, EventRequest
from ..dto.event_response import BatchIngestResponse, EventAcceptedResponse, EventResponse, QueryEventsResponse

logger = logging.getLogger("copilot_log_backend.api")
router = APIRouter(prefix="/v1/events", tags=["events"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def ingest_event(
    request: EventRequest,
    config: BackendConfig = Depends(require_api_key),
    container: ApplicationContainer = Depends(get_container),
) -> EventAcceptedResponse:
    try:
        event = container.ingest_event_use_case().execute(request.to_domain())
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _log_ingest(event.to_dict(), status="accepted")
    return EventAcceptedResponse(
        status="accepted",
        event_id=event.event_id,
        event=EventResponse.from_domain(event),
    )


@router.post("/batch")
def ingest_batch(
    request: BatchEventRequest,
    config: BackendConfig = Depends(require_api_key),
    container: ApplicationContainer = Depends(get_container),
) -> BatchIngestResponse:
    valid_events = []
    errors: list[BatchIngestError] = []

    for index, raw_event in enumerate(request.events):
        try:
            valid_events.append(EventRequest.model_validate(raw_event).to_domain())
        except ValidationError as exc:
            errors.append(
                BatchIngestError(
                    index=index,
                    event_id=str(raw_event.get("event_id")) if isinstance(raw_event, dict) else None,
                    error=str(exc.errors()),
                )
            )

    result = container.ingest_event_batch_use_case().execute(valid_events)
    combined = BatchIngestResult(
        accepted=result.accepted,
        rejected=result.rejected + len(errors),
        events=result.events,
        errors=[*errors, *result.errors],
    )
    for event in result.events:
        _log_ingest(event.to_dict(), status="accepted")
    return BatchIngestResponse.from_result(combined)


@router.get("")
def query_events(
    config: BackendConfig = Depends(require_api_key),
    container: ApplicationContainer = Depends(get_container),
    session_id: str | None = None,
    event_type: str | None = None,
    repo_name: str | None = None,
    actor: str | None = None,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
    limit: int = Query(100, ge=1),
) -> QueryEventsResponse:
    events = container.query_events_use_case().execute(
        session_id=session_id,
        event_type=event_type,
        repo_name=repo_name,
        actor=actor,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
        limit=limit,
    )
    return QueryEventsResponse.from_events(events)


def _log_ingest(event: dict[str, Any], *, status: str) -> None:
    logger.info(
        "event_ingested event_id=%s event_type=%s actor=%s repo_name=%s status=%s",
        event.get("event_id"),
        event.get("event_type"),
        event.get("actor"),
        event.get("repo_name"),
        status,
    )
