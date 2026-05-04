from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError

from app.config.dependency_injection import DependencyContainer
from app.domain.exception.domain_exceptions import DomainError
from app.domain.model.copilot_event import EventFilters, parse_timestamp
from app.entrypoints.api.dependencies import get_container, require_api_key
from app.entrypoints.api.dto.event_request import BatchEventRequest, EventRequest
from app.entrypoints.api.dto.event_response import (
    BatchIngestResponse,
    EventAcceptedResponse,
    EventResponse,
    PromptTraceResponse,
    QueryEventsResponse,
    SessionTraceResponse,
)
from app.usecase.ingest_batch_events_usecase import BatchIngestError, BatchIngestResult

router = APIRouter(prefix="/api/v1", tags=["events"], dependencies=[Depends(require_api_key)])


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
def ingest_event(
    request: EventRequest,
    container: DependencyContainer = Depends(get_container),
) -> EventAcceptedResponse:
    try:
        result = container.ingest_event_use_case().execute(request.to_domain())
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    container.metrics.increment("events.ingested")
    return EventAcceptedResponse(
        status="accepted",
        event_id=result.event.event_id,
        created=result.created,
        event=EventResponse.from_domain(result.event),
    )


@router.post("/events/batch")
def ingest_batch_events(
    request: BatchEventRequest,
    container: DependencyContainer = Depends(get_container),
) -> BatchIngestResponse:
    valid_events = []
    dto_errors: list[BatchIngestError] = []

    for index, raw_event in enumerate(request.events):
        try:
            valid_events.append(EventRequest.model_validate(raw_event).to_domain())
        except ValidationError as exc:
            dto_errors.append(
                BatchIngestError(
                    index=index,
                    event_id=str(raw_event.get("event_id")) if isinstance(raw_event, dict) else None,
                    error=str(exc.errors()),
                )
            )

    result = container.ingest_batch_events_use_case().execute(valid_events)
    combined = BatchIngestResult(
        accepted=result.accepted,
        rejected=result.rejected + len(dto_errors),
        created=result.created,
        duplicated=result.duplicated,
        events=result.events,
        errors=[*dto_errors, *result.errors],
    )
    container.metrics.increment("events.batch_accepted", result.accepted)
    return BatchIngestResponse.from_result(combined)


@router.get("/events")
def query_events(
    container: DependencyContainer = Depends(get_container),
    session_id: str | None = None,
    event_type: str | None = None,
    repository: str | None = None,
    user_id: str | None = None,
    userPrompt_id: str | None = None,
    parent_userPrompt_id: str | None = None,
    tool_name: str | None = None,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
    limit: int = Query(100, ge=1),
) -> QueryEventsResponse:
    filters = _event_filters(
        session_id=session_id,
        event_type=event_type,
        repository=repository,
        user_id=user_id,
        user_prompt_id=userPrompt_id,
        parent_user_prompt_id=parent_userPrompt_id,
        tool_name=tool_name,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
        limit=limit,
    )
    events = container.query_events_use_case().execute(filters)
    return QueryEventsResponse.from_events(events)


@router.get("/sessions/{session_id}")
def get_session_trace(
    session_id: str,
    container: DependencyContainer = Depends(get_container),
) -> SessionTraceResponse:
    session = container.get_session_trace_use_case().execute(session_id)
    return SessionTraceResponse.from_domain(session)


@router.get("/prompts/{userPrompt_id}/trace")
def get_prompt_trace(
    userPrompt_id: str,
    container: DependencyContainer = Depends(get_container),
) -> PromptTraceResponse:
    prompt = container.get_prompt_trace_use_case().execute(userPrompt_id)
    return PromptTraceResponse.from_domain(prompt)


def _event_filters(
    *,
    session_id: str | None,
    event_type: str | None,
    repository: str | None,
    user_id: str | None,
    user_prompt_id: str | None,
    parent_user_prompt_id: str | None,
    tool_name: str | None,
    from_timestamp: str | None,
    to_timestamp: str | None,
    limit: int,
) -> EventFilters:
    try:
        from_dt = _parse_optional_timestamp(from_timestamp)
        to_dt = _parse_optional_timestamp(to_timestamp)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return EventFilters(
        session_id=session_id,
        event_type=event_type,
        repository=repository,
        user_id=user_id,
        user_prompt_id=user_prompt_id,
        parent_user_prompt_id=parent_user_prompt_id,
        tool_name=tool_name,
        from_timestamp=from_dt,
        to_timestamp=to_dt,
        limit=limit,
    )


def _parse_optional_timestamp(value: Any) -> datetime | None:
    return parse_timestamp(value) if value not in (None, "") else None

