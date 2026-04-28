from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class GitContext:
    git_available: bool = False
    is_repo: bool = False
    repo_path: str | None = None
    repo_name: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    files_changed: list[str] = field(default_factory=list)
    error: str | None = None


def _run_git(git_executable: str, cwd: Path, *args: str) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            [git_executable, *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return False, str(exc)

    if completed.returncode != 0:
        return False, (completed.stderr or completed.stdout or "").strip()
    return True, completed.stdout.strip()


def _parse_changed_files(status_output: str) -> list[str]:
    changed_files: list[str] = []
    for line in status_output.splitlines():
        if not line.strip():
            continue
        candidate = line
        if len(candidate) >= 3 and candidate[2] == " ":
            candidate = candidate[3:]
        elif len(candidate) >= 2 and candidate[1] == " ":
            candidate = candidate[2:]
        candidate = candidate.strip()
        if " -> " in candidate:
            candidate = candidate.split(" -> ", 1)[1]
        changed_files.append(candidate.strip().strip('"'))
    return changed_files


def collect_git_context(cwd: str | Path | None = None) -> GitContext:
    working_directory = Path(cwd or Path.cwd()).resolve()
    git_executable = shutil.which("git")

    if not git_executable:
        return GitContext(error="git executable not found in PATH")

    context = GitContext(git_available=True)

    ok, repo_path = _run_git(git_executable, working_directory, "rev-parse", "--show-toplevel")
    if not ok:
        context.error = repo_path or "current directory is not a git repository"
        return context

    context.is_repo = True
    context.repo_path = repo_path
    context.repo_name = Path(repo_path).name if repo_path else None

    ok, branch = _run_git(git_executable, working_directory, "branch", "--show-current")
    context.git_branch = branch if ok and branch else None

    ok, commit = _run_git(git_executable, working_directory, "rev-parse", "HEAD")
    context.git_commit = commit if ok and commit else None

    ok, status_output = _run_git(git_executable, working_directory, "status", "--porcelain")
    if ok:
        context.files_changed = _parse_changed_files(status_output)

    return context
