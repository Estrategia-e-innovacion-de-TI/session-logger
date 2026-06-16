"""Similarity scoring between AI evidence and final committed code."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import re
from typing import Iterable


@dataclass
class SimilarityResult:
    exact_match_score: float
    normalized_match_score: float
    token_similarity_score: float
    block_similarity_score: float
    best_similarity_score: float
    exact_matched_lines: int
    fuzzy_matched_lines: int
    structural_matched_lines: int
    total_candidate_lines: int
    explanation: str

    def to_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


def compare_code(ai_evidence: str | Iterable[str], final_code: str | Iterable[str], threshold: float = 0.72) -> SimilarityResult:
    """Compare AI evidence text with final code or added lines."""

    evidence_text = _join_text(ai_evidence)
    final_text = _join_text(final_code)
    evidence_lines = _meaningful_lines(evidence_text)
    final_lines = _meaningful_lines(final_text)
    total = len(final_lines)

    if total == 0 or not evidence_lines:
        return SimilarityResult(0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, total, "No comparable code lines.")

    exact_set = set(evidence_lines)
    normalized_set = {_normalize_line(line) for line in evidence_lines}
    exact = 0
    normalized = 0
    fuzzy = 0

    for line in final_lines:
        if line in exact_set:
            exact += 1
        if _normalize_line(line) in normalized_set:
            normalized += 1
            continue
        if _best_line_ratio(line, evidence_lines) >= threshold:
            fuzzy += 1

    token_score = _token_similarity(evidence_text, final_text)
    block_score = SequenceMatcher(None, _normalize_block(evidence_text), _normalize_block(final_text)).ratio()
    exact_score = exact / total
    normalized_score = normalized / total
    fuzzy_score = fuzzy / total
    best = max(exact_score, normalized_score, token_score, block_score, fuzzy_score)
    structural = int(round(block_score * total))

    return SimilarityResult(
        exact_match_score=round(exact_score, 4),
        normalized_match_score=round(normalized_score, 4),
        token_similarity_score=round(token_score, 4),
        block_similarity_score=round(block_score, 4),
        best_similarity_score=round(best, 4),
        exact_matched_lines=exact,
        fuzzy_matched_lines=fuzzy,
        structural_matched_lines=structural,
        total_candidate_lines=total,
        explanation=(
            f"{exact} exact lines, {normalized} normalized lines, "
            f"{fuzzy} fuzzy lines over {total} final added lines."
        ),
    )


def compare_blocks(ai_blocks: Iterable[str], final_blocks: Iterable[str], threshold: float = 0.72) -> SimilarityResult:
    return compare_code("\n\n".join(ai_blocks), "\n\n".join(final_blocks), threshold=threshold)


def _join_text(value: str | Iterable[str]) -> str:
    if isinstance(value, str):
        return value
    return "\n".join(str(item) for item in value)


def _meaningful_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if line.strip()]


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", "", line).lower()


def _normalize_block(text: str) -> str:
    return "\n".join(_normalize_line(line) for line in _meaningful_lines(text))


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|==|!=|<=|>=|[-+*/%=(){}\[\],.:]", text))


def _token_similarity(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _best_line_ratio(line: str, evidence_lines: list[str]) -> float:
    normalized = _normalize_line(line)
    return max((SequenceMatcher(None, normalized, _normalize_line(candidate)).ratio() for candidate in evidence_lines), default=0.0)
