from __future__ import annotations

from pathlib import Path

from notebook_diff_normalizer import normalize_notebook


ROOT = Path(__file__).resolve().parents[1]


def test_normalizes_notebook_ignoring_outputs_and_metadata() -> None:
    lines = normalize_notebook(ROOT / "tests" / "fixtures" / "sample_notebook_cells.json")

    assert "import math" in lines
    assert "result = math.sqrt(4)" in lines
    assert "volatile output" not in "\n".join(lines)
    assert "volatile-code" not in "\n".join(lines)


def test_can_include_outputs_when_requested() -> None:
    lines = normalize_notebook(ROOT / "tests" / "fixtures" / "sample_notebook_cells.json", include_outputs=True)

    assert "volatile output" in "\n".join(lines)
