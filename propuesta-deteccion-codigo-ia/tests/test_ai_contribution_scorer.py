from __future__ import annotations

from ai_contribution_scorer import score_contribution


def test_calculates_ai_min_and_ai_max() -> None:
    result = score_contribution(
        total_added_lines=10,
        exact_matched_lines=2,
        fuzzy_matched_lines=4,
        structural_matched_lines=2,
        indirect_evidence_lines=2,
        evidence_types=["direct_code_evidence", "file_touch_evidence"],
    )

    assert result.ai_min_percent == 20.0
    assert result.ai_max_percent == 65.0
    assert result.confidence_label == "high_ai_evidence"


def test_handles_no_added_lines() -> None:
    result = score_contribution(
        total_added_lines=0,
        exact_matched_lines=0,
        fuzzy_matched_lines=0,
        structural_matched_lines=0,
        indirect_evidence_lines=0,
        evidence_types=[],
    )

    assert result.ai_min_percent == 0.0
    assert result.ai_max_percent == 0.0
    assert result.confidence_label == "no_evidence"
