from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.model.copilot_event import CopilotEvent, EventFilters

from .models import CopilotEventModel


class PostgresEventRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def save(self, event: CopilotEvent) -> CopilotEvent:
        with self.session_factory() as session:
            existing = _find_model_by_event_id(session, event.event_id)
            if existing is not None:
                return _to_domain(existing)

            model = _to_model(event)
            session.add(model)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = _find_model_by_event_id(session, event.event_id)
                if existing is None:
                    raise
                return _to_domain(existing)
            session.refresh(model)
            return _to_domain(model)

    def save_batch(self, events: list[CopilotEvent]) -> list[CopilotEvent]:
        return [self.save(event) for event in events]

    def find_by_event_id(self, event_id: str) -> CopilotEvent | None:
        with self.session_factory() as session:
            model = _find_model_by_event_id(session, event_id)
            return _to_domain(model) if model is not None else None

    def find_by_session_id(self, session_id: str) -> list[CopilotEvent]:
        query = (
            select(CopilotEventModel)
            .where(CopilotEventModel.session_id == session_id)
            .order_by(CopilotEventModel.timestamp.asc())
        )
        with self.session_factory() as session:
            return [_to_domain(model) for model in session.scalars(query).all()]

    def find_by_user_prompt_id(self, user_prompt_id: str) -> list[CopilotEvent]:
        query = (
            select(CopilotEventModel)
            .where(CopilotEventModel.user_prompt_id == user_prompt_id)
            .order_by(CopilotEventModel.timestamp.asc())
        )
        with self.session_factory() as session:
            return [_to_domain(model) for model in session.scalars(query).all()]

    def find_by_parent_userPrompt_id(self, parent_userPrompt_id: str) -> list[CopilotEvent]:
        query = (
            select(CopilotEventModel)
            .where(CopilotEventModel.parent_user_prompt_id == parent_userPrompt_id)
            .order_by(CopilotEventModel.timestamp.asc())
        )
        with self.session_factory() as session:
            return [_to_domain(model) for model in session.scalars(query).all()]

    def find_events(self, filters: EventFilters) -> list[CopilotEvent]:
        query = _apply_filters(select(CopilotEventModel), filters)
        query = query.order_by(CopilotEventModel.timestamp.desc()).limit(filters.limit)
        with self.session_factory() as session:
            return [_to_domain(model) for model in session.scalars(query).all()]

    def health(self) -> bool:
        try:
            with self.session_factory() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


def _find_model_by_event_id(session: Session, event_id: str) -> CopilotEventModel | None:
    return session.scalar(select(CopilotEventModel).where(CopilotEventModel.event_id == event_id))


def _apply_filters(
    query: Select[tuple[CopilotEventModel]],
    filters: EventFilters,
) -> Select[tuple[CopilotEventModel]]:
    if filters.session_id:
        query = query.where(CopilotEventModel.session_id == filters.session_id)
    if filters.event_type:
        query = query.where(CopilotEventModel.event_type == filters.event_type)
    if filters.repository:
        query = query.where(CopilotEventModel.repository == filters.repository)
    if filters.user_id:
        query = query.where(CopilotEventModel.user_id == filters.user_id)
    if filters.user_prompt_id:
        query = query.where(CopilotEventModel.user_prompt_id == filters.user_prompt_id)
    if filters.parent_user_prompt_id:
        query = query.where(CopilotEventModel.parent_user_prompt_id == filters.parent_user_prompt_id)
    if filters.tool_name:
        query = query.where(CopilotEventModel.tool_name == filters.tool_name)
    if filters.from_timestamp:
        query = query.where(CopilotEventModel.timestamp >= filters.from_timestamp)
    if filters.to_timestamp:
        query = query.where(CopilotEventModel.timestamp <= filters.to_timestamp)
    return query


def _to_model(event: CopilotEvent) -> CopilotEventModel:
    return CopilotEventModel(
        event_id=event.event_id,
        session_id=event.session_id,
        event_type=event.event_type,
        timestamp=event.timestamp,
        user_id=event.user_id,
        repository=event.repository,
        branch=event.branch,
        workspace=event.workspace,
        user_prompt_id=event.user_prompt_id,
        parent_user_prompt_id=event.parent_user_prompt_id,
        tool_name=event.tool_name,
        prompt_text=event.prompt_text,
        assistant_response_summary=event.assistant_response_summary,
        tool_input_summary=event.tool_input_summary,
        tool_result_summary=event.tool_result_summary,
        status=event.status,
        duration_ms=event.duration_ms,
        files_touched=list(event.files_touched),
        commands_executed=list(event.commands_executed),
        metadata_payload=dict(event.metadata),
        raw_payload=event.raw_payload,
        created_at=event.created_at,
    )


def _to_domain(model: CopilotEventModel) -> CopilotEvent:
    return CopilotEvent(
        event_id=model.event_id,
        session_id=model.session_id,
        event_type=model.event_type,
        timestamp=model.timestamp,
        user_id=model.user_id,
        repository=model.repository,
        branch=model.branch,
        workspace=model.workspace,
        user_prompt_id=model.user_prompt_id,
        parent_user_prompt_id=model.parent_user_prompt_id,
        tool_name=model.tool_name,
        prompt_text=model.prompt_text,
        assistant_response_summary=model.assistant_response_summary,
        tool_input_summary=model.tool_input_summary,
        tool_result_summary=model.tool_result_summary,
        status=model.status,
        duration_ms=model.duration_ms,
        files_touched=_list_or_empty(model.files_touched),
        commands_executed=_list_or_empty(model.commands_executed),
        metadata=model.metadata_payload or {},
        raw_payload=model.raw_payload,
        created_at=model.created_at,
    )


def _list_or_empty(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]

