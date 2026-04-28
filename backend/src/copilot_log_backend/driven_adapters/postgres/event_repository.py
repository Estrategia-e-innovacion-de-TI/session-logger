from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select, text
from sqlalchemy.orm import Session, sessionmaker

from copilot_log_backend.domain.entities.event import EventRecord, parse_timestamp

from .models import EventModel


class PostgresEventRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def save(self, event: EventRecord) -> EventRecord:
        model = _to_model(event)
        with self.session_factory() as session:
            merged = session.merge(model)
            session.commit()
            session.refresh(merged)
            return _to_entity(merged)

    def save_many(self, events: list[EventRecord]) -> list[EventRecord]:
        if not events:
            return []
        with self.session_factory() as session:
            merged = [session.merge(_to_model(event)) for event in events]
            session.commit()
            for model in merged:
                session.refresh(model)
            return [_to_entity(model) for model in merged]

    def find(
        self,
        *,
        session_id: str | None,
        event_type: str | None,
        repo_name: str | None,
        actor: str | None,
        from_timestamp: str | None,
        to_timestamp: str | None,
        limit: int,
    ) -> list[EventRecord]:
        query: Select[tuple[EventModel]] = select(EventModel)
        if session_id:
            query = query.where(EventModel.session_id == session_id)
        if event_type:
            query = query.where(EventModel.event_type == event_type)
        if repo_name:
            query = query.where(EventModel.repo_name == repo_name)
        if actor:
            query = query.where(EventModel.actor == actor)
        if from_timestamp:
            query = query.where(EventModel.timestamp >= parse_timestamp(from_timestamp))
        if to_timestamp:
            query = query.where(EventModel.timestamp <= parse_timestamp(to_timestamp))
        query = query.order_by(EventModel.timestamp.desc()).limit(limit)

        with self.session_factory() as session:
            return [_to_entity(model) for model in session.scalars(query).all()]

    def health(self) -> bool:
        try:
            with self.session_factory() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


def _to_model(event: EventRecord) -> EventModel:
    return EventModel(
        event_id=event.event_id,
        session_id=event.session_id,
        event_type=event.event_type,
        timestamp=event.timestamp,
        user_prompt=event.user_prompt,
        prompt_hash=event.prompt_hash,
        repo_path=event.repo_path,
        repo_name=event.repo_name,
        git_branch=event.git_branch,
        git_commit=event.git_commit,
        working_directory=event.working_directory,
        actor=event.actor,
        files_changed=list(event.files_changed),
        tool_name=event.tool_name,
        command=event.command,
        status=event.status,
        error=event.error,
        raw_payload=event.raw_payload,
        metadata_payload=dict(event.metadata),
        created_at=event.created_at,
    )


def _to_entity(model: EventModel) -> EventRecord:
    return EventRecord(
        event_id=model.event_id,
        session_id=model.session_id,
        event_type=model.event_type,
        timestamp=model.timestamp,
        user_prompt=model.user_prompt,
        prompt_hash=model.prompt_hash,
        repo_path=model.repo_path,
        repo_name=model.repo_name,
        git_branch=model.git_branch,
        git_commit=model.git_commit,
        working_directory=model.working_directory,
        actor=model.actor,
        files_changed=_list_or_empty(model.files_changed),
        tool_name=model.tool_name,
        command=model.command,
        status=model.status,
        error=model.error,
        raw_payload=model.raw_payload,
        metadata=model.metadata_payload or {},
        created_at=model.created_at,
    )


def _list_or_empty(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]
