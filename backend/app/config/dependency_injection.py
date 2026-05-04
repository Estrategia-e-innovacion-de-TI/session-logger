from __future__ import annotations

from functools import cached_property

from app.driven_adapters.observability.metrics import InMemoryMetrics
from app.driven_adapters.postgres.analytics_repository_adapter import PostgresAnalyticsRepository
from app.driven_adapters.postgres.database import (
    create_postgres_engine,
    create_session_factory,
    run_migrations,
)
from app.driven_adapters.postgres.event_repository_adapter import PostgresEventRepository
from app.driven_adapters.security.api_key_validator import ApiKeyValidator
from app.driven_adapters.security.sanitizer import RegexSanitizer
from app.usecase.get_prompt_impact_usecase import GetPromptImpactUseCase
from app.usecase.get_prompt_trace_usecase import GetPromptTraceUseCase
from app.usecase.get_repository_activity_usecase import GetRepositoryActivityUseCase
from app.usecase.get_session_summary_usecase import GetSessionSummaryUseCase
from app.usecase.get_session_trace_usecase import GetSessionTraceUseCase
from app.usecase.get_tool_usage_analytics_usecase import GetToolUsageAnalyticsUseCase
from app.usecase.health_check_usecase import HealthCheckUseCase
from app.usecase.ingest_batch_events_usecase import IngestBatchEventsUseCase
from app.usecase.ingest_event_usecase import IngestEventUseCase
from app.usecase.query_events_usecase import QueryEventsUseCase

from .settings import BackendSettings


class DependencyContainer:
    def __init__(self, settings: BackendSettings) -> None:
        self.settings = settings

    @cached_property
    def engine(self):
        engine = create_postgres_engine(self.settings.database_url)
        if self.settings.auto_migrate:
            run_migrations(engine)
        return engine

    @cached_property
    def session_factory(self):
        return create_session_factory(self.engine)

    @cached_property
    def event_repository(self) -> PostgresEventRepository:
        return PostgresEventRepository(self.session_factory)

    @cached_property
    def analytics_repository(self) -> PostgresAnalyticsRepository:
        return PostgresAnalyticsRepository(self.session_factory)

    @cached_property
    def sanitizer(self) -> RegexSanitizer:
        return RegexSanitizer()

    @cached_property
    def api_key_validator(self) -> ApiKeyValidator:
        return ApiKeyValidator(self.settings.api_keys)

    @cached_property
    def metrics(self) -> InMemoryMetrics:
        return InMemoryMetrics()

    def ingest_event_use_case(self) -> IngestEventUseCase:
        return IngestEventUseCase(
            self.event_repository,
            self.sanitizer,
            allow_unknown_event_types=self.settings.allow_unknown_event_types,
        )

    def ingest_batch_events_use_case(self) -> IngestBatchEventsUseCase:
        return IngestBatchEventsUseCase(
            self.event_repository,
            self.sanitizer,
            allow_unknown_event_types=self.settings.allow_unknown_event_types,
        )

    def query_events_use_case(self) -> QueryEventsUseCase:
        return QueryEventsUseCase(self.event_repository, max_limit=self.settings.query_limit)

    def get_session_trace_use_case(self) -> GetSessionTraceUseCase:
        return GetSessionTraceUseCase(self.event_repository)

    def get_prompt_trace_use_case(self) -> GetPromptTraceUseCase:
        return GetPromptTraceUseCase(self.event_repository)

    def get_tool_usage_analytics_use_case(self) -> GetToolUsageAnalyticsUseCase:
        return GetToolUsageAnalyticsUseCase(self.analytics_repository)

    def get_repository_activity_use_case(self) -> GetRepositoryActivityUseCase:
        return GetRepositoryActivityUseCase(self.analytics_repository)

    def get_prompt_impact_use_case(self) -> GetPromptImpactUseCase:
        return GetPromptImpactUseCase(self.analytics_repository)

    def get_session_summary_use_case(self) -> GetSessionSummaryUseCase:
        return GetSessionSummaryUseCase(self.analytics_repository)

    def health_check_use_case(self) -> HealthCheckUseCase:
        return HealthCheckUseCase(self.event_repository, storage="postgres")
