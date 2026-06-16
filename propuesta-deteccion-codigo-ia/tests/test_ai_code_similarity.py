from __future__ import annotations

from ai_code_similarity import compare_code


def test_detects_exact_matches() -> None:
    evidence = "def add_numbers(a, b):\n    return a + b\n"
    final = "def add_numbers(a, b):\n    return a + b\n"

    result = compare_code(evidence, final)

    assert result.exact_match_score == 1.0
    assert result.exact_matched_lines == 2
    assert result.best_similarity_score == 1.0


def test_detects_approximate_matches() -> None:
    evidence = "def add_numbers(a, b):\n    return a + b\n"
    final = "def add_numbers(a,b):\n    return a+b\n"

    result = compare_code(evidence, final)

    assert result.exact_match_score == 0.0
    assert result.normalized_match_score == 1.0
    assert result.best_similarity_score == 1.0
