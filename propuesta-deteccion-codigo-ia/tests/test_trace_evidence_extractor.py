from __future__ import annotations

from pathlib import Path

from trace_evidence_extractor import extract_evidence, summarize_evidence
from trace_loader import load_traces


ROOT = Path(__file__).resolve().parents[1]


def test_identifies_prompts_tools_and_files() -> None:
    events = load_traces([ROOT / "tests" / "fixtures" / "sample_trace_minimal.json"])
    evidence = extract_evidence(events)
    summary = summarize_evidence(evidence)

    assert summary["evidence_by_type"]["assistant_text_evidence"] >= 1
    assert summary["evidence_by_type"]["direct_code_evidence"] >= 1
    assert summary["evidence_by_type"]["file_touch_evidence"] >= 1
    assert "summary_report.py" in summary["files"]


def test_marks_no_code_trace_as_indirect() -> None:
    events = load_traces([ROOT / "Trace-2dbae2-2026-06-10 10_28_39.json"])
    evidence = extract_evidence(events)

    assert any(item.evidence_type == "weak_indirect_evidence" for item in evidence)
    assert not any(item.direct for item in evidence)
