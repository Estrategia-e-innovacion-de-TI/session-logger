from __future__ import annotations

from fastapi import APIRouter, Depends

from copilot_log_backend.application.container import ApplicationContainer

from ..dependencies import get_container

router = APIRouter(tags=["health"])


@router.get("/health")
def health(container: ApplicationContainer = Depends(get_container)) -> dict[str, str]:
    status = container.health_check_use_case(check_database=False).execute()
    return {"status": status.status, "storage": status.storage}
