"""Estimate AI contribution ranges from similarity and evidence signals."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


DEFAULT_WEIGHTS = {
    "exact_match": 1.0,
    "fuzzy_match": 0.75,
    "structural_match": 0.5,
    "indirect_evidence": 0.25,
}


@dataclass
class ContributionScore:
    ai_min_percent: float
    ai_max_percent: float
    confidence_score: float
    confidence_label: str
    evidence_types: list[str]
    explanation: str

    def to_dict(self) -> dict[str, float | str | list[str]]:
        return asdict(self)


def score_contribution(
    total_added_lines: int,
    exact_matched_lines: int,
    fuzzy_matched_lines: int,
    structural_matched_lines: int,
    indirect_evidence_lines: int,
    evidence_types: Iterable[str],
    weights: dict[str, float] | None = None,
) -> ContributionScore:
    """Calculate a defensible AI contribution range.

    AI_min is strict exact-line reuse. AI_max includes fuzzy, structural, and
    indirect evidence with lower weights. The output is capped at 100%.
    """

    evidence_type_list = sorted(set(evidence_types))
    if total_added_lines <= 0:
        return ContributionScore(
            ai_min_percent=0.0,
            ai_max_percent=0.0,
            confidence_score=0.0,
            confidence_label="no_evidence",
            evidence_types=evidence_type_list,
            explanation="No added lines were available for attribution.",
        )

    active_weights = dict(DEFAULT_WEIGHTS)
    if weights:
        active_weights.update(weights)

    ai_min = exact_matched_lines / total_added_lines
    weighted_lines = (
        exact_matched_lines * active_weights["exact_match"]
        + fuzzy_matched_lines * active_weights["fuzzy_match"]
        + structural_matched_lines * active_weights["structural_match"]
        + indirect_evidence_lines * active_weights["indirect_evidence"]
    )
    ai_max = min(1.0, weighted_lines / total_added_lines)
    confidence_score = _confidence_score(evidence_type_list, ai_max, total_added_lines)

    return ContributionScore(
        ai_min_percent=round(ai_min * 100, 2),
        ai_max_percent=round(ai_max * 100, 2),
        confidence_score=round(confidence_score, 3),
        confidence_label=_label(ai_max, confidence_score, evidence_type_list),
        evidence_types=evidence_type_list,
        explanation=(
            "AI_min uses exact matches only. AI_max weights exact, fuzzy, "
            "structural, and indirect evidence against total added lines."
        ),
    )


def _confidence_score(evidence_types: list[str], ai_max: float, total_added_lines: int) -> float:
    type_weights = {
        "direct_code_evidence": 0.40,
        "assistant_text_evidence": 0.20,
        "file_touch_evidence": 0.15,
        "command_evidence": 0.08,
        "temporal_evidence": 0.07,
        "weak_indirect_evidence": 0.04,
    }
    type_score = sum(type_weights.get(item, 0.0) for item in evidence_types)
    volume_score = min(0.15, total_added_lines / 200)
    similarity_score = min(0.30, ai_max * 0.30)
    return min(1.0, type_score + volume_score + similarity_score)


def _label(ai_max: float, confidence_score: float, evidence_types: list[str]) -> str:
    if not evidence_types or confidence_score == 0:
        return "no_evidence"
    if ai_max < 0.20:
        return "low_ai_evidence"
    if ai_max < 0.50:
        return "medium_ai_evidence"
    if ai_max < 0.80:
        return "high_ai_evidence"
    return "very_high_ai_evidence"
