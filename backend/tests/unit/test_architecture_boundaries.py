from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _source_under(path: str) -> str:
    root = BACKEND_ROOT / path
    return "\n".join(
        file.read_text(encoding="utf-8")
        for file in root.rglob("*.py")
        if "__pycache__" not in file.parts
    ).lower()


def test_domain_has_no_framework_or_infrastructure_imports() -> None:
    source = _source_under("app/domain")

    forbidden = ("fastapi", "sqlalchemy", "psycopg", "pydantic", "postgres")
    assert not any(name in source for name in forbidden)


def test_usecases_do_not_depend_on_entrypoints_or_driven_adapters() -> None:
    source = _source_under("app/usecase")

    forbidden = ("fastapi", "sqlalchemy", "psycopg", "pydantic", "driven_adapters", "entrypoints")
    assert not any(name in source for name in forbidden)


def test_domain_declares_expected_gateway_contracts() -> None:
    event_repository = (BACKEND_ROOT / "app/domain/gateway/event_repository.py").read_text(
        encoding="utf-8"
    )
    analytics_repository = (BACKEND_ROOT / "app/domain/gateway/analytics_repository.py").read_text(
        encoding="utf-8"
    )

    for method in (
        "save",
        "save_batch",
        "find_by_event_id",
        "find_by_session_id",
        "find_by_parent_userPrompt_id",
    ):
        assert f"def {method}" in event_repository

    for method in (
        "get_tool_usage",
        "get_repository_activity",
        "get_prompt_impact",
        "get_session_summary",
    ):
        assert f"def {method}" in analytics_repository
