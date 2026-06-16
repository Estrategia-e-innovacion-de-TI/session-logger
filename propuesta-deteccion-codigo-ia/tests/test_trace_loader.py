from __future__ import annotations

from pathlib import Path

from trace_loader import load_traces


ROOT = Path(__file__).resolve().parents[1]


def test_loads_trace_with_missing_fields() -> None:
    events = load_traces([ROOT / "tests" / "fixtures" / "sample_trace_minimal.json"])

    assert len(events) == 2
    assert events[0].session_id == "sess-fixture-001"
    assert events[0].tool_name == "replace_string_in_file"
    assert "summary_report.py" in events[0].files_touched


def test_loads_real_otlp_trace_shape() -> None:
    events = load_traces([ROOT / "Trace-3fff4d-2026-06-10 15_13_18.json"])

    assert len(events) == 12
    assert any(event.tool_name == "replace_string_in_file" for event in events)
    assert any("summary_report.py" in file for event in events for file in event.files_touched)
