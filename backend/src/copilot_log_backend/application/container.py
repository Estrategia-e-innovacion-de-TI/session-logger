from __future__ import annotations

from functools import cached_property

from copilot_log_backend.domain.gateways.event_repository import EventRepository
from copilot_log_backend.driven_adapters.jsonl.event_repository import JsonlEventRepository
from copilot_log_backend.driven_adapters.postgres.database import (
    create_postgres_engine,
    create_session_factory,
    run_migrations,
)
from copilot_log_backend.driven_adapters.postgres.event_repository import PostgresEventRepository
from copilot_log_backend.driven_adapters.security.sanitizer import RegexSanitizer
from copilot_log_backend.usecases.health_check import HealthCheckUseCase
from copilot_log_backend.usecases.ingest_event import IngestEventUseCase
from copilot_log_backend.usecases.ingest_event_batch import IngestEventBatchUseCase
from copilot_log_backend.usecases.query_events import QueryEventsUseCase

from .config import BackendConfig


class ApplicationContainer:
    def __init__(self, config: BackendConfig) -> None:
        self.config = config

    @cached_property
    def sanitizer(self) -> RegexSanitizer:
        return RegexSanitizer()

    @cached_property
    def repository(self) -> EventRepository:
        if self.config.storage == "jsonl":
            return JsonlEventRepository(self.config.events_dir)
        engine = create_postgres_engine(self.config.database_url)
        if self.config.auto_migrate:
            run_migrations(engine)
        return PostgresEventRepository(create_session_factory(engine))

    def ingest_event_use_case(self) -> IngestEventUseCase:
        return IngestEventUseCase(
            self.repository,
            self.sanitizer,
            allow_unknown_event_types=self.config.allow_unknown_event_types,
        )

    def ingest_event_batch_use_case(self) -> IngestEventBatchUseCase:
        return IngestEventBatchUseCase(
            self.repository,
            self.sanitizer,
            allow_unknown_event_types=self.config.allow_unknown_event_types,
        )

    def query_events_use_case(self) -> QueryEventsUseCase:
        return QueryEventsUseCase(self.repository, max_limit=self.config.query_limit)

    def health_check_use_case(self, *, check_database: bool = False) -> HealthCheckUseCase:
        return HealthCheckUseCase(
            self.repository if check_database else None,
            storage=self.config.storage,
            check_database=check_database,
        )
