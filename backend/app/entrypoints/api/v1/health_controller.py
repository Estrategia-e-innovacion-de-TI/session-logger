from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config.dependency_injection import DependencyContainer
from app.entrypoints.api.dependencies import get_container

router = APIRouter(tags=["health"])


@router.get("/health")
def health(container: DependencyContainer = Depends(get_container)) -> dict[str, str]:
    status = container.health_check_use_case().execute(check_storage=False)
    return {"status": status.status, "storage": status.storage}

