from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import ResearchFlowError


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ResearchFlowError(f"Git command failed in {repo}: git {' '.join(args)}\n{detail}")
    # Porcelain status uses leading spaces as data; trimming the left side can
    # corrupt paths and bypass scope rules.
    return result.stdout.rstrip()


def require_git_repo(repo: Path) -> None:
    if not repo.is_dir() or git(repo, "rev-parse", "--is-inside-work-tree", check=False) != "true":
        raise ResearchFlowError(f"Formal experiments require a Git repository: {repo}")


def head(repo: Path) -> str:
    require_git_repo(repo)
    return git(repo, "rev-parse", "HEAD")


def branch(repo: Path) -> str | None:
    value = git(repo, "branch", "--show-current")
    return value or None


def commit_exists(repo: Path, commit: str) -> bool:
    result = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{commit}^{{commit}}"], capture_output=True)
    return result.returncode == 0


def dirty_paths(repo: Path) -> list[str]:
    output = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    return [line[3:].replace("\\", "/") for line in output.splitlines() if len(line) >= 4]


def diff_hash(repo: Path) -> str | None:
    tracked = subprocess.run(["git", "-C", str(repo), "diff", "--binary", "HEAD"], capture_output=True).stdout
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
    result = subprocess.run(["git", "-C", str(repo), "worktree", "add", "--detach", str(target), baseline], capture_output=True, text=True)
    if result.returncode:
        raise ResearchFlowError(f"Cannot create experiment worktree {target}: {result.stderr.strip()}")
    return str(target)
