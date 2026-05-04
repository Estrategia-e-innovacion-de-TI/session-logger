from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config.dependency_injection import DependencyContainer
from app.domain.gateway.analytics_repository import AnalyticsFilters
from app.domain.model.copilot_event import parse_timestamp
from app.entrypoints.api.dependencies import get_container, require_api_key
from app.entrypoints.api.dto.analytics_response import (
    PromptImpactResponse,
    RepositoryActivityResponse,
    SessionSummaryResponse,
    ToolUsageResponse,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"], dependencies=[Depends(require_api_key)])


@router.get("/tool-usage")
def get_tool_usage(
    container: DependencyContainer = Depends(get_container),
    session_id: str | None = None,
    repository: str | None = None,
    user_id: str | None = None,
    tool_name: str | None = None,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
    limit: int = Query(100, ge=1),
) -> ToolUsageResponse:
    filters = _analytics_filters(
        session_id=session_id,
        repository=repository,
        user_id=user_id,
        tool_name=tool_name,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
        limit=limit,
    )
    return ToolUsageResponse.from_domain(container.get_tool_usage_analytics_use_case().execute(filters))


@router.get("/repository-activity")
def get_repository_activity(
    container: DependencyContainer = Depends(get_container),
    session_id: str | None = None,
    repository: str | None = None,
    user_id: str | None = None,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
    limit: int = Query(100, ge=1),
) -> RepositoryActivityResponse:
    filters = _analytics_filters(
        session_id=session_id,
        repository=repository,
        user_id=user_id,
        tool_name=None,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
        limit=limit,
    )
    return RepositoryActivityResponse.from_domain(
        container.get_repository_activity_use_case().execute(filters)
    )


@router.get("/prompt-impact")
def get_prompt_impact(
    container: DependencyContainer = Depends(get_container),
    session_id: str | None = None,
    repository: str | None = None,
    user_id: str | None = None,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
    limit: int = Query(100, ge=1),
) -> PromptImpactResponse:
    filters = _analytics_filters(
        session_id=session_id,
        repository=repository,
        user_id=user_id,
        tool_name=None,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
        limit=limit,
    )
    return PromptImpactResponse.from_domain(container.get_prompt_impact_use_case().execute(filters))


@router.get("/session-summary")
def get_session_summary(
    container: DependencyContainer = Depends(get_container),
    session_id: str | None = None,
    repository: str | None = None,
    user_id: str | None = None,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
    limit: int = Query(100, ge=1),
) -> SessionSummaryResponse:
    filters = _analytics_filters(
        session_id=session_id,
        repository=repository,
        user_id=user_id,
        tool_name=None,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
        limit=limit,
    )
    return SessionSummaryResponse.from_domain(container.get_session_summary_use_case().execute(filters))


def _analytics_filters(
    *,
    session_id: str | None,
    repository: str | None,
    user_id: str | None,
    tool_name: str | None,
    from_timestamp: str | None,
    to_timestamp: str | None,
    limit: int,
) -> AnalyticsFilters:
    try:
        from_dt = _parse_optional_timestamp(from_timestamp)
        to_dt = _parse_optional_timestamp(to_timestamp)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AnalyticsFilters(
        session_id=session_id,
        repository=repository,
        user_id=user_id,
        tool_name=tool_name,
        from_timestamp=from_dt,
        to_timestamp=to_dt,
        limit=limit,
    )


def _parse_optional_timestamp(value: Any) -> datetime | None:
    return parse_timestamp(value) if value not in (None, "") else None

