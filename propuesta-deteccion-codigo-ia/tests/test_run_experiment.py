from __future__ import annotations

import json
from pathlib import Path

from run_experiment import main


ROOT = Path(__file__).resolve().parents[1]


def test_run_experiment_dry_run_with_fixtures(tmp_path: Path) -> None:
    config = {
        "trace_files": ["tests/fixtures/sample_trace_minimal.json"],
        "target_repository": {
            "name": "quantum-computing-experiments",
            "owner": "Estrategia-e-innovacion-de-TI",
            "local_path": "../quantum-computing-experiments",
            "branch": "main",
            "commit": None,
            "commit_range": None
        },
        "analysis": {
            "include_notebooks": True,
            "include_notebook_outputs": False,
            "similarity_threshold": 0.72,
            "temporal_window_minutes": 180
        },
        "scoring_weights": {
            "exact_match": 1.0,
            "fuzzy_match": 0.75,
            "structural_match": 0.5,
            "indirect_evidence": 0.25
        },
        "outputs": {
            "directory": str(tmp_path)
        }
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    assert main(["--config", str(config_path), "--dry-run"]) == 0
    assert (tmp_path / "ai_contribution_summary.json").exists()
    assert (tmp_path / "ai_contribution_by_commit.csv").exists()
    assert (tmp_path / "ai_contribution_by_file.csv").exists()
    assert (tmp_path / "experiment_report.md").exists()
