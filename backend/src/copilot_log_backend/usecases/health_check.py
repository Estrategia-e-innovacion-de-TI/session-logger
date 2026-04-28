from __future__ import annotations

from dataclasses import dataclass

from copilot_log_backend.domain.gateways.event_repository import EventRepository


@dataclass(slots=True)
class HealthStatus:
    status: str
    storage: str
    database: str | None = None


class HealthCheckUseCase:
    def __init__(
        self,
        repository: EventRepository | None,
        *,
        storage: str,
        check_database: bool = False,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.check_database = check_database

    def execute(self) -> HealthStatus:
        database_status = None
        if self.check_database and self.repository is not None:
            database_status = "ok" if self.repository.health() else "unavailable"
        return HealthStatus(status="ok", storage=self.storage, database=database_status)
