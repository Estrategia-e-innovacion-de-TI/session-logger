from __future__ import annotations

from app.domain.gateway.analytics_repository import AnalyticsFilters, AnalyticsRepository, SessionSummary


class GetSessionSummaryUseCase:
    def __init__(self, analytics_repository: AnalyticsRepository) -> None:
        self.analytics_repository = analytics_repository

    def execute(self, filters: AnalyticsFilters) -> list[SessionSummary]:
        return self.analytics_repository.get_session_summary(filters)

