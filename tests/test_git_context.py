from pathlib import Path

from copilot_session_logger.git_context import collect_git_context


def test_collect_git_context_when_git_is_missing(monkeypatch) -> None:
    monkeypatch.setattr("copilot_session_logger.git_context.shutil.which", lambda _: None)

    context = collect_git_context(Path.cwd())

    assert context.git_available is False
    assert context.error == "git executable not found in PATH"


def test_collect_git_context_reads_repository_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("copilot_session_logger.git_context.shutil.which", lambda _: "git")

    def fake_run(command, cwd, capture_output, text, check):
        args = tuple(command[1:])
        outputs = {
            ("rev-parse", "--show-toplevel"): (0, str(tmp_path), ""),
            ("branch", "--show-current"): (0, "main", ""),
            ("rev-parse", "HEAD"): (0, "abc123", ""),
            ("status", "--porcelain"): (0, " M README.md\nA  src/app.py", ""),
        }
        returncode, stdout, stderr = outputs[args]

        class Result:
            def __init__(self):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        return Result()

    monkeypatch.setattr("copilot_session_logger.git_context.subprocess.run", fake_run)

    context = collect_git_context(tmp_path)

    assert context.git_available is True
    assert context.is_repo is True
    assert context.repo_path == str(tmp_path)
    assert context.repo_name == tmp_path.name
    assert context.git_branch == "main"
    assert context.git_commit == "abc123"
    assert context.files_changed == ["README.md", "src/app.py"]

