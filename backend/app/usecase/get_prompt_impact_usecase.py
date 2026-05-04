from __future__ import annotations

from app.domain.gateway.analytics_repository import AnalyticsFilters, AnalyticsRepository, PromptImpact


class GetPromptImpactUseCase:
    def __init__(self, analytics_repository: AnalyticsRepository) -> None:
        self.analytics_repository = analytics_repository

    def execute(self, filters: AnalyticsFilters) -> list[PromptImpact]:
        return self.analytics_repository.get_prompt_impact(filters)

