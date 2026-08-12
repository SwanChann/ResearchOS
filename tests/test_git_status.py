from __future__ import annotations

import subprocess
from pathlib import Path

from researchflow.cli import main
from researchflow.gitops import inspect_git_state
from researchflow.project import add_project


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _init(repo: Path, *, commit: bool = False) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "TEST User")
    _git(repo, "config", "user.email", "test@example.invalid")
    if commit:
        (repo / "tracked.txt").write_text("TEST\n", encoding="utf-8")
        _git(repo, "add", "tracked.txt")
        _git(repo, "commit", "-m", "TEST checkpoint")


def test_git_state_non_git_missing_and_unborn(tmp_path):
    non_git = tmp_path / "plain"
    non_git.mkdir()
    state = inspect_git_state(non_git)
    assert state.reachable is True
    assert state.is_repository is False
    assert state.recoverable_checkpoint is False

    missing = inspect_git_state(tmp_path / "missing")
    assert missing.reachable is False
    assert missing.is_repository is False

    unborn = tmp_path / "unborn"
    _init(unborn)
    state = inspect_git_state(unborn)
    assert state.is_repository is True
    assert state.unborn_head is True
    assert state.head_commit is None
    assert state.branch == "main"
    assert state.recoverable_checkpoint is False


def test_git_state_reports_missing_git_executable(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()

    def missing_git(*args, **kwargs):
        raise FileNotFoundError("TEST git missing")

    monkeypatch.setattr("researchflow.gitops.subprocess.run", missing_git)
    state = inspect_git_state(repo)
    assert state.reachable is True
    assert state.is_repository is False
    assert state.recoverable_checkpoint is False
    assert "cannot execute Git" in state.error


def test_git_state_clean_dirty_untracked_and_detached(tmp_path):
    repo = tmp_path / "repo"
    _init(repo, commit=True)
    clean = inspect_git_state(repo)
    assert clean.clean is True
    assert clean.tracked_modifications == 0
    assert clean.untracked_files == 0
    assert clean.recoverable_checkpoint is True

    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("new\n", encoding="utf-8")
    dirty = inspect_git_state(repo)
    assert dirty.clean is False
    assert dirty.tracked_modifications == 1
    assert dirty.untracked_files == 1

    _git(repo, "restore", "tracked.txt")
    (repo / "untracked.txt").unlink()
    _git(repo, "checkout", "--detach")
    detached = inspect_git_state(repo)
    assert detached.detached is True
    assert detached.branch is None
    assert detached.head_commit


def test_doctor_warns_for_unborn_and_dirty_without_changing_default_exit_code(rf_env, capsys):
    _init(rf_env["repo"])
    add_project("toy", rf_env["repo"])
    assert main(["--project", "toy", "doctor"]) == 0
    output = capsys.readouterr().out
    assert "WARN project toy Git HEAD/checkpoint" in output
    assert "unborn HEAD" in output
    assert main(["--project", "toy", "doctor", "--strict"]) == 1

    (rf_env["repo"] / "untracked.txt").write_text("new\n", encoding="utf-8")
    assert main(["--project", "toy", "project", "show"]) == 0
    output = capsys.readouterr().out
    assert "unborn" in output
    assert "untracked_files: 1" in output
    assert "No Git commit" not in output
