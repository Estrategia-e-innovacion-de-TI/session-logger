from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CopilotEventModel(Base):
    __tablename__ = "copilot_events"
    __table_args__ = (
        Index("idx_copilot_events_repository_timestamp", "repository", "timestamp"),
        Index("idx_copilot_events_parent_prompt_event_type", "parent_userPrompt_id", "event_type"),
        Index("idx_copilot_events_metadata_gin", "metadata", postgresql_using="gin"),
        Index("idx_copilot_events_raw_payload_gin", "raw_payload", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    repository: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    branch: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_prompt_id: Mapped[str | None] = mapped_column(
        "userPrompt_id", Text, nullable=True, index=True, quote=True
    )
    parent_user_prompt_id: Mapped[str | None] = mapped_column(
        "parent_userPrompt_id", Text, nullable=True, index=True, quote=True
    )
    tool_name: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    assistant_response_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    files_touched: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    files_added: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    commands_executed: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    raw_payload: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

