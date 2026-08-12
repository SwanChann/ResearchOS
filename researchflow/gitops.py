from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ResearchFlowError


def git_command(repo: Path, *args: str) -> list[str]:
    """Build a Git command that trusts only this explicitly selected repository."""
    safe_repo = repo.resolve().as_posix()
    return ["git", "-c", f"safe.directory={safe_repo}", "-C", str(repo), *args]


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(git_command(repo, *args), capture_output=True, text=True)
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ResearchFlowError(f"Git command failed in {repo}: git {' '.join(args)}\n{detail}")
    # Porcelain status uses leading spaces as data; trimming the left side can
    # corrupt paths and bypass scope rules.
    return result.stdout.rstrip()


def require_git_repo(repo: Path) -> None:
    if not repo.is_dir() or git(repo, "rev-parse", "--is-inside-work-tree", check=False) != "true":
        raise ResearchFlowError(f"Formal experiments require a Git repository: {repo}")


@dataclass
class GitState:
    path: str
    reachable: bool
    is_repository: bool
    head_exists: bool
    unborn_head: bool
    branch: str | None
    detached: bool
    head_commit: str | None
    clean: bool | None
    tracked_modifications: int
    untracked_files: int
    recoverable_checkpoint: bool
    error: str | None = None

    @property
    def warning(self) -> bool:
        return (
            not self.reachable
            or not self.is_repository
            or not self.head_exists
            or not bool(self.clean)
            or not self.recoverable_checkpoint
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "reachable": self.reachable,
            "is_repository": self.is_repository,
            "head_exists": self.head_exists,
            "head_state": "unborn" if self.unborn_head else "commit" if self.head_exists else "none",
            "branch": self.branch,
            "detached": self.detached,
            "head_commit": self.head_commit,
            "clean": self.clean,
            "tracked_modifications": self.tracked_modifications,
            "untracked_files": self.untracked_files,
            "recoverable_checkpoint": self.recoverable_checkpoint,
            "error": self.error,
        }


def inspect_git_state(repo: Path) -> GitState:
    """Return repository and checkpoint state without mutating Git or the worktree."""
    resolved = repo.expanduser().resolve()
    if not resolved.is_dir():
        return GitState(str(resolved), False, False, False, False, None, False, None, None, 0, 0, False, "path is not a directory")
    try:
        inside = subprocess.run(
            git_command(resolved, "rev-parse", "--is-inside-work-tree"),
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return GitState(
            str(resolved), True, False, False, False, None, False, None, None,
            0, 0, False, f"cannot execute Git: {exc}",
        )
    if inside.returncode or inside.stdout.strip() != "true":
        detail = inside.stderr.strip() or "not a Git worktree"
        return GitState(str(resolved), True, False, False, False, None, False, None, None, 0, 0, False, detail)
    head_result = subprocess.run(git_command(resolved, "rev-parse", "--verify", "HEAD"), capture_output=True, text=True)
    head_exists = head_result.returncode == 0
    head_commit = head_result.stdout.strip() if head_exists else None
    branch_result = subprocess.run(git_command(resolved, "symbolic-ref", "--quiet", "--short", "HEAD"), capture_output=True, text=True)
    branch_name = branch_result.stdout.strip() or None
    detached = head_exists and branch_name is None
    status_result = subprocess.run(
        git_command(resolved, "status", "--porcelain=v1", "--untracked-files=all"),
        capture_output=True,
        text=True,
    )
    if status_result.returncode:
        detail = status_result.stderr.strip() or "cannot read Git status"
        return GitState(str(resolved), True, True, head_exists, not head_exists, branch_name, detached, head_commit, None, 0, 0, head_exists, detail)
    lines = [line for line in status_result.stdout.splitlines() if line]
    untracked = sum(1 for line in lines if line.startswith("??"))
    tracked = sum(1 for line in lines if not line.startswith("??"))
    return GitState(
        str(resolved), True, True, head_exists, not head_exists, branch_name, detached,
        head_commit, not lines, tracked, untracked, head_exists, None,
    )


def head(repo: Path) -> str:
    require_git_repo(repo)
    return git(repo, "rev-parse", "HEAD")


def branch(repo: Path) -> str | None:
    value = git(repo, "branch", "--show-current")
    return value or None


def commit_exists(repo: Path, commit: str) -> bool:
    result = subprocess.run(git_command(repo, "cat-file", "-e", f"{commit}^{{commit}}"), capture_output=True)
    return result.returncode == 0


def dirty_paths(repo: Path) -> list[str]:
    output = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    return [line[3:].replace("\\", "/") for line in output.splitlines() if len(line) >= 4]


def diff_hash(repo: Path) -> str | None:
    tracked = subprocess.run(git_command(repo, "diff", "--binary", "HEAD"), capture_output=True).stdout
    untracked = "\n".join(path for path in dirty_paths(repo) if not (repo / path).exists() or git(repo, "ls-files", "--error-unmatch", path, check=False) == "")
    payload = tracked + untracked.encode()
    return hashlib.sha256(payload).hexdigest() if payload else None


def changed_paths(repo: Path, baseline: str) -> list[str]:
    output = git(repo, "diff", "--name-only", f"{baseline}..HEAD")
    paths = [line.replace("\\", "/") for line in output.splitlines() if line]
    return sorted(set(paths + dirty_paths(repo)))


def _within(path: str, rule: str) -> bool:
    normalized = rule.strip("/").replace("\\", "/")
    return path == normalized or path.startswith(normalized + "/")


@dataclass
class ScopeResult:
    changed: list[str]
    frozen_violations: list[str]
    outside_allowed: list[str]

    @property
    def ok(self) -> bool:
        return not self.frozen_violations and not self.outside_allowed


def check_scope(paths: list[str], allowed: list[str], frozen: list[str]) -> ScopeResult:
    frozen_violations = [path for path in paths if any(_within(path, rule) for rule in frozen)]
    outside_allowed = [path for path in paths if not any(_within(path, rule) for rule in allowed)] if allowed else list(paths)
    return ScopeResult(paths, frozen_violations, outside_allowed)


def create_worktree(repo: Path, target: Path, baseline: str, dry_run: bool = False) -> str:
    require_git_repo(repo)
    if not commit_exists(repo, baseline):
        raise ResearchFlowError(f"Baseline commit does not exist in {repo}: {baseline}")
    if target.exists():
        raise ResearchFlowError(f"Experiment worktree already exists: {target}")
    command = f"git -C {repo} worktree add --detach {target} {baseline}"
    if dry_run:
        return f"DRY-RUN: {command}"
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(git_command(repo, "worktree", "add", "--detach", str(target), baseline), capture_output=True, text=True)
    if result.returncode:
        raise ResearchFlowError(f"Cannot create experiment worktree {target}: {result.stderr.strip()}")
    return str(target)
