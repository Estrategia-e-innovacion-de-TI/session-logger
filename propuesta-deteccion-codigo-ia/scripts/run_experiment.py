"""Run the AI contribution detection PoC."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

from ai_code_similarity import compare_code
from ai_contribution_scorer import score_contribution
from git_diff_extractor import CommitDiff, DiffHunk, FileDiff, GitDiffError, extract_commits, filter_supported_files
from trace_evidence_extractor import AIEvidence, extract_evidence, summarize_evidence
from trace_loader import NormalizedEvent, load_traces


DEFAULT_CONFIG = Path("config/experiment_config.example.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Estimate AI contribution from traces and Git diffs.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to experiment JSON config.")
    parser.add_argument("--dry-run", action="store_true", help="Use local fixtures instead of Git.")
    args = parser.parse_args(argv)

    config_path = Path(args.config).resolve()
    config = _read_config(config_path)
    poc_root = config_path.parent.parent if config_path.parent.name == "config" else Path.cwd()
    output_dir = _resolve_output_dir(config, poc_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    trace_paths = _resolve_trace_files(config.get("trace_files", []), config_path, poc_root)
    events = load_traces(trace_paths)
    evidence = extract_evidence(events)

    try:
        commits = _load_commits(config, config_path, poc_root, dry_run=args.dry_run)
    except GitDiffError as exc:
        _write_trace_only_outputs(output_dir, events, evidence, str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary, rows_by_commit, rows_by_file = analyze(events, evidence, commits, config)
    _write_outputs(output_dir, summary, rows_by_commit, rows_by_file, events, evidence)
    print(f"Experiment completed. Outputs written to {output_dir}")
    return 0


def analyze(
    events: list[NormalizedEvent],
    evidence: list[AIEvidence],
    commits: list[CommitDiff],
    config: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    analysis = config.get("analysis", {})
    weights = config.get("scoring_weights", {})
    threshold = float(analysis.get("similarity_threshold", 0.72))
    include_notebooks = bool(analysis.get("include_notebooks", True))
    evidence_text = "\n\n".join(_texts_for_similarity(evidence))
    evidence_types = [item.evidence_type for item in evidence]

    rows_by_commit: list[dict[str, Any]] = []
    rows_by_file: list[dict[str, Any]] = []

    for commit in commits:
        supported_files = filter_supported_files(commit.files, include_notebooks=include_notebooks)
        commit_exact = 0
        commit_fuzzy = 0
        commit_structural = 0
        commit_indirect = 0
        commit_added = 0
        best_similarity = 0.0

        for file_diff in supported_files:
            added_lines = [line for hunk in file_diff.hunks for line in hunk.added_lines]
            final_text = "\n".join(added_lines)
            similarity = compare_code(evidence_text, final_text, threshold=threshold)
            direct_file_evidence = _evidence_for_file(evidence, file_diff.path)
            indirect_lines = len(added_lines) if direct_file_evidence else 0
            score = score_contribution(
                total_added_lines=len(added_lines),
                exact_matched_lines=similarity.exact_matched_lines,
                fuzzy_matched_lines=similarity.fuzzy_matched_lines,
                structural_matched_lines=similarity.structural_matched_lines,
                indirect_evidence_lines=indirect_lines,
                evidence_types=evidence_types,
                weights=weights,
            )

            rows_by_file.append(
                {
                    "commit_hash": commit.commit_hash,
                    "file_path": file_diff.path,
                    "added_lines": len(added_lines),
                    "deleted_lines": file_diff.deleted_lines,
                    "best_similarity_score": similarity.best_similarity_score,
                    "exact_match_score": similarity.exact_match_score,
                    "normalized_match_score": similarity.normalized_match_score,
                    "token_similarity_score": similarity.token_similarity_score,
                    "block_similarity_score": similarity.block_similarity_score,
                    "ai_min_percent": score.ai_min_percent,
                    "ai_max_percent": score.ai_max_percent,
                    "confidence_score": score.confidence_score,
                    "confidence_label": score.confidence_label,
                    "evidence_types": "|".join(score.evidence_types),
                    "explanation": score.explanation,
                }
            )

            commit_exact += similarity.exact_matched_lines
            commit_fuzzy += similarity.fuzzy_matched_lines
            commit_structural += similarity.structural_matched_lines
            commit_indirect += indirect_lines
            commit_added += len(added_lines)
            best_similarity = max(best_similarity, similarity.best_similarity_score)

        commit_score = score_contribution(
            total_added_lines=commit_added,
            exact_matched_lines=commit_exact,
            fuzzy_matched_lines=commit_fuzzy,
            structural_matched_lines=commit_structural,
            indirect_evidence_lines=commit_indirect,
            evidence_types=evidence_types,
            weights=weights,
        )
        rows_by_commit.append(
            {
                "commit_hash": commit.commit_hash,
                "author": commit.author,
                "date": commit.date,
                "message": commit.message.replace("\n", " "),
                "files_modified": "|".join(commit.files_modified),
                "lines_added": commit.lines_added,
                "lines_deleted": commit.lines_deleted,
                "supported_added_lines": commit_added,
                "best_similarity_score": best_similarity,
                "ai_min_percent": commit_score.ai_min_percent,
                "ai_max_percent": commit_score.ai_max_percent,
                "confidence_score": commit_score.confidence_score,
                "confidence_label": commit_score.confidence_label,
                "evidence_types": "|".join(commit_score.evidence_types),
                "explanation": commit_score.explanation,
            }
        )

    summary = {
        "trace_event_count": len(events),
        "evidence_summary": summarize_evidence(evidence),
        "commit_count": len(commits),
        "commit_scores": rows_by_commit,
        "method": "range_estimate_not_absolute_attribution",
    }
    return summary, rows_by_commit, rows_by_file


def _read_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def _resolve_trace_files(trace_files: list[str], config_path: Path, poc_root: Path) -> list[Path]:
    resolved: list[Path] = []
    for trace_file in trace_files:
        path = Path(trace_file)
        candidates = [
            path,
            config_path.parent / path,
            poc_root / path,
            Path.cwd() / path,
        ]
        match = next((candidate.resolve() for candidate in candidates if candidate.exists()), None)
        if match is None:
            raise FileNotFoundError(f"Trace file not found: {trace_file}")
        resolved.append(match)
    return resolved


def _resolve_output_dir(config: dict[str, Any], poc_root: Path) -> Path:
    configured = Path(config.get("outputs", {}).get("directory", "outputs"))
    if configured.is_absolute():
        return configured
    return (poc_root / configured).resolve()


def _load_commits(config: dict[str, Any], config_path: Path, poc_root: Path, dry_run: bool) -> list[CommitDiff]:
    if dry_run:
        patch_path = poc_root / "tests" / "fixtures" / "sample_commit_diff.patch"
        return [_commit_from_patch_fixture(patch_path)]

    repo_config = config.get("target_repository", {})
    repo_path = _resolve_repo_path(repo_config.get("local_path", ""), config_path, poc_root)
    return extract_commits(
        repo_path,
        commit=repo_config.get("commit"),
        commit_range=repo_config.get("commit_range"),
        limit=int(repo_config.get("limit", 10)),
    )


def _resolve_repo_path(local_path: str, config_path: Path, poc_root: Path) -> Path:
    if not local_path:
        raise GitDiffError("target_repository.local_path is required when not using --dry-run.")
    raw = Path(local_path)
    candidates = [
        raw,
        Path.cwd() / raw,
        config_path.parent / raw,
        poc_root / raw,
        poc_root.parent / raw,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise GitDiffError(f"Configured local repository was not found: {local_path}")


def _commit_from_patch_fixture(patch_path: Path) -> CommitDiff:
    patch = patch_path.read_text(encoding="utf-8")
    file_hunks: dict[str, list[DiffHunk]] = {}
    current_file: str | None = None
    current_hunk: DiffHunk | None = None

    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            file_hunks.setdefault(current_file, [])
        elif line.startswith("@@") and current_file:
            current_hunk = DiffHunk(header=line, added_lines=[], deleted_lines=[])
            file_hunks[current_file].append(current_hunk)
        elif current_hunk and line.startswith("+") and not line.startswith("+++"):
            current_hunk.added_lines.append(line[1:])
        elif current_hunk and line.startswith("-") and not line.startswith("---"):
            current_hunk.deleted_lines.append(line[1:])

    files = [
        FileDiff(
            path=path,
            added_lines=sum(len(hunk.added_lines) for hunk in hunks),
            deleted_lines=sum(len(hunk.deleted_lines) for hunk in hunks),
            hunks=hunks,
        )
        for path, hunks in file_hunks.items()
    ]
    return CommitDiff(
        commit_hash="dry-run-fixture",
        author="fixture",
        date="2026-06-10T00:00:00Z",
        message="Dry-run fixture commit",
        files_modified=[file.path for file in files],
        lines_added=sum(file.added_lines for file in files),
        lines_deleted=sum(file.deleted_lines for file in files),
        files=files,
        patch=patch,
    )


def _texts_for_similarity(evidence: list[AIEvidence]) -> list[str]:
    texts: list[str] = []
    for item in evidence:
        texts.extend(item.snippets)
        if item.evidence_type == "assistant_text_evidence":
            texts.extend(item.snippets)
    return [text for text in texts if text]


def _evidence_for_file(evidence: list[AIEvidence], file_path: str) -> bool:
    normalized = file_path.replace("\\", "/").lower()
    basename = Path(file_path).name.lower()
    for item in evidence:
        for evidence_file in item.files:
            candidate = evidence_file.replace("\\", "/").lower()
            if normalized in candidate or basename in candidate:
                return True
    return False


def _write_outputs(
    output_dir: Path,
    summary: dict[str, Any],
    rows_by_commit: list[dict[str, Any]],
    rows_by_file: list[dict[str, Any]],
    events: list[NormalizedEvent],
    evidence: list[AIEvidence],
) -> None:
    (output_dir / "ai_contribution_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(output_dir / "ai_contribution_by_commit.csv", rows_by_commit)
    _write_csv(output_dir / "ai_contribution_by_file.csv", rows_by_file)
    (output_dir / "experiment_report.md").write_text(
        _render_report(summary, rows_by_commit, rows_by_file, events, evidence),
        encoding="utf-8",
    )


def _write_trace_only_outputs(output_dir: Path, events: list[NormalizedEvent], evidence: list[AIEvidence], error: str) -> None:
    summary = {
        "trace_event_count": len(events),
        "evidence_summary": summarize_evidence(evidence),
        "commit_count": 0,
        "error": error,
        "method": "trace_only_due_to_git_error",
    }
    _write_outputs(output_dir, summary, [], [], events, evidence)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _render_report(
    summary: dict[str, Any],
    rows_by_commit: list[dict[str, Any]],
    rows_by_file: list[dict[str, Any]],
    events: list[NormalizedEvent],
    evidence: list[AIEvidence],
) -> str:
    lines = [
        "# Experiment Report",
        "",
        "## Trace Analysis",
        f"- Normalized events: {len(events)}",
        f"- Evidence items: {len(evidence)}",
        f"- Evidence by type: {summary.get('evidence_summary', {}).get('evidence_by_type', {})}",
        f"- Files referenced by traces: {summary.get('evidence_summary', {}).get('files', [])}",
        "",
        "## Commit Results",
    ]
    if rows_by_commit:
        for row in rows_by_commit:
            lines.append(
                f"- `{row['commit_hash']}`: AI range {row['ai_min_percent']}%-{row['ai_max_percent']}%, "
                f"confidence `{row['confidence_label']}`, files `{row['files_modified']}`"
            )
    else:
        lines.append("- No commit results were produced.")
    if summary.get("error"):
        lines.extend(["", "## Execution Warning", str(summary["error"])])
    lines.extend(
        [
            "",
            "## Interpretation",
            "The range is an evidence-based estimate, not a definitive claim that a line was generated by AI.",
            "AI_min counts exact reuse. AI_max also includes fuzzy, structural, and indirect signals with lower weights.",
        ]
    )
    if rows_by_file:
        lines.extend(["", "## File Results"])
        for row in rows_by_file:
            lines.append(
                f"- `{row['file_path']}`: {row['added_lines']} added lines, "
                f"best similarity {row['best_similarity_score']}, AI range {row['ai_min_percent']}%-{row['ai_max_percent']}%."
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
