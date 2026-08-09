from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_config, research_home
from .errors import ResearchFlowError
from .io import atomic_text, read_markdown_record, read_yaml, utc_now, write_yaml
from .schema import validate_record

WORKSPACE_DIRS = (
    "memory/observations", "memory/hypotheses", "memory/decisions",
    "evidence/papers/pdf", "evidence/papers/analysis",
    "evidence/repos/manifests", "evidence/repos/notes",
    "experiments/cards", "experiments/reports", "runs", "notes/daily",
)

KNOWLEDGE = """# Knowledge Index

## Current State
`memory/current-state.md`

## Assumptions
`memory/assumptions.md`

## Observations
`memory/observations/`

## Hypotheses
`memory/hypotheses/`

## Decisions
`memory/decisions/`

## Papers
`evidence/papers/index.jsonl`

## Code Evidence
`evidence/repos/`

## Experiments
`experiments/registry.jsonl`

## Runs
`runs/registry.jsonl`
"""

AGENT_RULES = """# Project Agent Protocol

At startup:

1. Read this file, `KNOWLEDGE.md`, and `memory/current-state.md`.
2. If code work is involved, inspect the configured research repository and its Git status.
3. Classify the question and retrieve task-specific evidence; do not load all history.
4. Separate verified literature/code, observations, experimental results, hypotheses, inference, and needs-verification.
5. Create no scientific claim from model memory, smoke output, fixtures, or unregistered metrics.
6. Before a run, validate the experiment card, approval, Git provenance, scope, budget, and stop conditions.
7. Never run a full GPU job, push, merge, delete data, or operate a real robot without explicit approval.
8. Write durable findings back as Observation, Hypothesis, Run, or Decision records with provenance.
"""

CURRENT_STATE = """# Current State

## Main Research Question

Not set.

## Current Stage

Project initialized.

## Active Hypothesis

None.

## Active Experiment

None.

## Current Best Baseline

Not recorded.

## Open Blockers

None recorded.

## Next Action

Record the main research question and retrieve relevant evidence.
"""


def project_path(project_id: str, config: dict[str, Any] | None = None) -> Path:
    return research_home(config) / ".projects" / project_id


def add_project(project_id: str, repo: Path, name: str | None = None, config: dict[str, Any] | None = None) -> Path:
    if not project_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in project_id):
        raise ResearchFlowError("Project ID must contain only lowercase letters, numbers, '-' or '_'.")
    repo = repo.expanduser().resolve()
    if not repo.is_dir():
        raise ResearchFlowError(f"Research repository does not exist: {repo}")
    workspace = project_path(project_id, config)
    if workspace.exists():
        raise ResearchFlowError(f"Project already exists: {project_id} ({workspace})")
    for relative in WORKSPACE_DIRS:
        (workspace / relative).mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "id": project_id,
        "name": name or project_id,
        "repo": {"local": str(repo)},
        "compute": {"default_machine": "local"},
        "paths": {},
        "created": utc_now(),
    }
    validate_record("project", data)
    write_yaml(workspace / "project.yaml", data)
    atomic_text(workspace / "AGENTS.md", AGENT_RULES)
    atomic_text(workspace / "KNOWLEDGE.md", KNOWLEDGE)
    atomic_text(workspace / "memory" / "current-state.md", CURRENT_STATE)
    atomic_text(workspace / "memory" / "assumptions.md", "# Assumptions\n\nNo assumptions recorded.\n")
    for path in ("evidence/papers/index.jsonl", "experiments/registry.jsonl", "runs/registry.jsonl"):
        atomic_text(workspace / path, "")
    return workspace


def list_projects(config: dict[str, Any] | None = None) -> list[str]:
    root = research_home(config) / ".projects"
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if (path / "project.yaml").is_file())


@dataclass
class ResearchProject:
    root: Path
    data: dict[str, Any]

    @classmethod
    def open(cls, project_id: str, config: dict[str, Any] | None = None) -> "ResearchProject":
        root = project_path(project_id, config or load_config())
        if not root.is_dir():
            raise ResearchFlowError(f"Unknown project: {project_id}. Run: rf project list")
        data = read_yaml(root / "project.yaml")
        validate_record("project", data)
        return cls(root, data)

    @property
    def repo(self) -> Path:
        return Path(self.data["repo"]["local"])

    def status(self) -> dict[str, Any]:
        _, body = read_markdown_record(self.root / "memory" / "current-state.md") if (self.root / "memory" / "current-state.md").read_text(encoding="utf-8").startswith("---\n") else ({}, (self.root / "memory" / "current-state.md").read_text(encoding="utf-8"))
        return {"id": self.data["id"], "name": self.data["name"], "repo": str(self.repo), "current_state": body.strip()}

    @property
    def evidence(self):
        from .evidence import EvidenceStore
        return EvidenceStore(self)
