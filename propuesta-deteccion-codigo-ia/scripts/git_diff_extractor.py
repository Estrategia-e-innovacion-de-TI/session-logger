"""Extract commit and diff information from a local Git repository."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import subprocess
from typing import Iterable


class GitDiffError(RuntimeError):
    """Raised when Git information cannot be extracted."""


@dataclass
class DiffHunk:
    header: str
    added_lines: list[str]
    deleted_lines: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class FileDiff:
    path: str
    added_lines: int
    deleted_lines: int
    hunks: list[DiffHunk]

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "added_lines": self.added_lines,
            "deleted_lines": self.deleted_lines,
            "hunks": [hunk.to_dict() for hunk in self.hunks],
        }


@dataclass
class CommitDiff:
    commit_hash: str
    author: str
    date: str
    message: str
    files_modified: list[str]
    lines_added: int
    lines_deleted: int
    files: list[FileDiff]
    patch: str

    def to_dict(self) -> dict[str, object]:
        return {
            "commit_hash": self.commit_hash,
            "author": self.author,
            "date": self.date,
            "message": self.message,
            "files_modified": self.files_modified,
            "lines_added": self.lines_added,
            "lines_deleted": self.lines_deleted,
            "files": [file.to_dict() for file in self.files],
            "patch": self.patch,
        }


def extract_commits(repo_path: str | Path, commit: str | None = None, commit_range: str | None = None, limit: int = 10) -> list[CommitDiff]:
    """Extract one commit, a range, or the latest commit."""

    repo = _validate_repo(repo_path)
    commit_ids = list_commits(repo, commit=commit, commit_range=commit_range, limit=limit)
    return [extract_commit(repo, commit_id) for commit_id in commit_ids]


def list_commits(repo_path: str | Path, commit: str | None = None, commit_range: str | None = None, limit: int = 10) -> list[str]:
    repo = _validate_repo(repo_path)
    if commit:
        return [commit]
    if commit_range:
        output = _run_git(repo, ["rev-list", "--reverse", commit_range])
        return [line.strip() for line in output.splitlines() if line.strip()]
    output = _run_git(repo, ["rev-parse", "HEAD"])
    return [output.strip()][:limit]


def extract_commit(repo_path: str | Path, commit: str = "HEAD") -> CommitDiff:
    repo = _validate_repo(repo_path)
    meta = _run_git(repo, ["show", "-s", "--format=%H%n%an%n%aI%n%B", commit]).splitlines()
    commit_hash = meta[0] if len(meta) > 0 else commit
    author = meta[1] if len(meta) > 1 else ""
    date = meta[2] if len(meta) > 2 else ""
    message = "\n".join(meta[3:]).strip()
    numstat = _run_git(repo, ["show", "--numstat", "--format=", commit])
    patch = _run_git(repo, ["show", "--patch", "--format=", "--no-ext-diff", commit])
    file_counts = _parse_numstat(numstat)
    hunks = _parse_patch(patch)

    files: list[FileDiff] = []
    for path, counts in file_counts.items():
        files.append(
            FileDiff(
                path=path,
                added_lines=counts[0],
                deleted_lines=counts[1],
                hunks=hunks.get(path, []),
            )
        )
    for path, path_hunks in hunks.items():
        if path not in file_counts:
            files.append(FileDiff(path=path, added_lines=sum(len(h.added_lines) for h in path_hunks), deleted_lines=sum(len(h.deleted_lines) for h in path_hunks), hunks=path_hunks))

    return CommitDiff(
        commit_hash=commit_hash,
        author=author,
        date=date,
        message=message,
        files_modified=[file.path for file in files],
        lines_added=sum(file.added_lines for file in files),
        lines_deleted=sum(file.deleted_lines for file in files),
        files=files,
        patch=patch,
    )


def diff_between(repo_path: str | Path, base: str, commit: str) -> str:
    repo = _validate_repo(repo_path)
    return _run_git(repo, ["diff", base, commit])


def _validate_repo(repo_path: str | Path) -> Path:
    repo = Path(repo_path).expanduser().resolve()
    if not repo.exists():
        raise GitDiffError(f"Repository path does not exist: {repo}")
    if not (repo / ".git").exists():
        raise GitDiffError(f"Path is not a Git repository: {repo}")
    return repo


def _run_git(repo: Path, args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise GitDiffError("Git executable was not found in PATH. Install Git or configure a local patch/dry-run experiment.") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        raise GitDiffError(f"Git command failed: git -C {repo} {' '.join(args)}\n{message}") from exc
    return completed.stdout


def _parse_numstat(text: str) -> dict[str, tuple[int, int]]:
    files: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added = _safe_int(parts[0])
        deleted = _safe_int(parts[1])
        path = parts[2]
        files[path] = (added, deleted)
    return files


def _parse_patch(patch: str) -> dict[str, list[DiffHunk]]:
    files: dict[str, list[DiffHunk]] = {}
    current_file: str | None = None
    current_hunk: DiffHunk | None = None

    for line in patch.splitlines():
        if line.startswith("diff --git "):
            current_file = None
            current_hunk = None
            continue
        if line.startswith("+++ b/"):
            current_file = line[6:]
            files.setdefault(current_file, [])
            continue
        if line.startswith("@@"):
            if current_file is None:
                continue
            current_hunk = DiffHunk(header=line, added_lines=[], deleted_lines=[])
            files[current_file].append(current_hunk)
            continue
        if current_hunk is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current_hunk.added_lines.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            current_hunk.deleted_lines.append(line[1:])

    return files


def _safe_int(value: str) -> int:
    if value == "-":
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def added_lines_by_file(commit: CommitDiff) -> dict[str, list[str]]:
    return {
        file.path: [line for hunk in file.hunks for line in hunk.added_lines]
        for file in commit.files
    }


def deleted_lines_by_file(commit: CommitDiff) -> dict[str, list[str]]:
    return {
        file.path: [line for hunk in file.hunks for line in hunk.deleted_lines]
        for file in commit.files
    }


def filter_supported_files(files: Iterable[FileDiff], include_notebooks: bool = True) -> list[FileDiff]:
    supported = []
    for file in files:
        if file.path.endswith(".py") or file.path.endswith("requirements.txt"):
            supported.append(file)
        elif include_notebooks and file.path.endswith(".ipynb"):
            supported.append(file)
    return supported
