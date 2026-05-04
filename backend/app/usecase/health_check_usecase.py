from __future__ import annotations

from dataclasses import dataclass

from app.domain.gateway.event_repository import EventRepository


@dataclass(frozen=True, slots=True)
class HealthStatus:
    status: str
    storage: str


class HealthCheckUseCase:
    def __init__(self, event_repository: EventRepository, *, storage: str = "configured") -> None:
        self.event_repository = event_repository
        self.storage = storage

    def execute(self, *, check_storage: bool = False) -> HealthStatus:
        if check_storage and not self.event_repository.health():
            return HealthStatus(status="degraded", storage=self.storage)
        return HealthStatus(status="ok", storage=self.storage)
