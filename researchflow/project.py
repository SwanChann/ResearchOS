from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import sys
from typing import Any

from .config import load_config, research_home
from .errors import ResearchFlowError
from .io import atomic_text, read_markdown_record, read_yaml, utc_now, write_yaml
from .schema import validate_record

WORKSPACE_DIRS = (
    ".research",
    ".research/evidence-graph/audits", ".research/corpus-gap/runs", ".research/migrations",
    "memory/observations", "memory/hypotheses", "memory/decisions",
    "memory/problems", "memory/gaps", "memory/claims",
    "evidence/papers/pdf", "evidence/papers/analysis",
    "evidence/corpora", "evidence/corpus-extractions",
    "evidence/repos/manifests", "evidence/repos/notes",
    "experiments/cards", "experiments/reports", "runs", "notes/daily", "skills",
)

SKILL_NAMES = (
    "retrieve-before-reason", "literature-query", "paper-deep-read", "code-evidence-query",
    "hypothesis-focus", "experiment-design", "experiment-review",
    "experiment-run", "result-analysis", "daily-log",
)

KNOWLEDGE = """# Knowledge Index

## Current State
`memory/current-state.md`

## Assumptions
`memory/assumptions.md`

## Observations
`memory/observations/`

## Problems
`memory/problems/`

## Gaps
`memory/gaps/`

## Hypotheses
`memory/hypotheses/`

## Claims
`memory/claims/`

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

## Evidence Graph
`.research/evidence-graph/edges.yaml`
"""

AGENT_RULES = """# Project Agent Protocol

At startup:

1. Read this file, `KNOWLEDGE.md`, and `memory/current-state.md`.
   Run `rf knowledge check`; rebuild only the delimited generated region when stale.
2. If code work is involved, inspect the configured research repository and its Git status.
3. Read the relevant `skills/<name>/SKILL.md`, classify the question, and retrieve task-specific evidence; do not load all history.
4. Separate verified literature/code, observations, experimental results, hypotheses, inference, and needs-verification.
5. Create no scientific claim from model memory, smoke output, fixtures, or unregistered metrics.
6. Before a run, validate the experiment card, approval, Git provenance, scope, budget, and stop conditions.
7. Never run a full GPU job, push, merge, delete data, or operate a real robot without explicit approval.
8. Write durable findings back as Observation, Hypothesis, Run, or Decision records with provenance.
9. Use CLI scaffold/preflight and the Artifact registry for formal products. Contract/source/hash checks and human review do not establish reproduction or scientific truth.
10. Treat workspace snapshots, Git checkpoints, Zotero, and external asset backups as separate recovery boundaries.
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

POLICY = {
    "schema_version": 1,
    "permissions": {
        "read": "allow", "search": "allow", "edit_experiment_worktree": "allow",
        "unit_test": "allow", "smoke_test": "allow", "experiment_commit": "allow",
        "pilot_gpu_run": "configurable", "full_gpu_run": "human",
        "merge_baseline": "human", "git_push": "human",
        "delete_dataset": "deny", "delete_checkpoint": "deny",
        "real_robot_execution": "human", "safety_critical_control_edit": "human",
    },
}


def skill_source_dir() -> Path:
    candidates = [Path(__file__).resolve().parent.parent / "skills", Path(sys.prefix) / "share" / "researchflow" / "skills"]
    for candidate in candidates:
        if all((candidate / name / "SKILL.md").is_file() for name in SKILL_NAMES):
            return candidate
    raise ResearchFlowError("Built-in ResearchFlow skills are missing. Reinstall the package.")


def update_current_state(project: "ResearchProject", section: str, value: str) -> None:
    path = project.root / "memory" / "current-state.md"
    text = path.read_text(encoding="utf-8")
    pattern = rf"(## {re.escape(section)}\n\n)(.*?)(?=\n\n## |\Z)"
    updated, count = re.subn(pattern, lambda match: match.group(1) + value.strip(), text, count=1, flags=re.DOTALL)
    if count != 1:
        raise ResearchFlowError(f"Current-state section is missing: {section} ({path})")
    atomic_text(path, updated.rstrip() + "\n")


def parse_current_state(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    return {match.group(1): match.group(2).strip() for match in re.finditer(r"^## (.+?)\n\n(.*?)(?=\n\n## |\Z)", text, re.MULTILINE | re.DOTALL)}


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
    write_yaml(workspace / "policy.yaml", POLICY)
    source_skills = skill_source_dir()
    for skill in SKILL_NAMES:
        target = workspace / "skills" / skill
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_skills / skill / "SKILL.md", target / "SKILL.md")
    for path in ("evidence/papers/index.jsonl", "experiments/registry.jsonl", "runs/registry.jsonl"):
        atomic_text(workspace / path, "")
    project = ResearchProject(workspace, data)
    from .artifact import ArtifactStore
    from .knowledge import KnowledgeStore
    artifacts = ArtifactStore(project)
    artifacts.initialize()
    from .evidence_graph import EvidenceGraphStore
    graph = EvidenceGraphStore(project)
    graph.initialize()
    graph.rebuild()
    KnowledgeStore(project).rebuild()
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

    def status(self, *, verbose: bool = False) -> dict[str, Any]:
        from .io import read_jsonl
        from .gitops import inspect_git_state
        from .snapshot import list_snapshots
        state = parse_current_state(self.root / "memory" / "current-state.md")
        experiment_events = read_jsonl(self.root / "experiments" / "registry.jsonl")
        run_events = [item for item in read_jsonl(self.root / "runs" / "registry.jsonl") if item.get("event") == "registered"]
        decisions = sorted((self.root / "memory" / "decisions").glob("DEC-*.md"))
        from .knowledge import KnowledgeStore
        knowledge = KnowledgeStore(self)
        result = {
            "id": self.data["id"], "name": self.data["name"], "repo": str(self.repo),
            "workspace": str(self.root),
            "authority_boundaries": {
                "researchflow_workspace": "authoritative research-control records",
                "independent_repo": "authoritative executable research code and Git history",
                "global_config": "local machine defaults and aliases; not a project record",
                "zotero": "authoritative bibliography, PDFs, collections, tags, annotations, and citation formatting",
            },
            "repo_state": inspect_git_state(self.repo).as_dict(),
            "snapshot_state": {
                "default_directory": str(research_home() / ".snapshots" / self.data["id"]),
                "count": len([item for item in list_snapshots(self) if item.get("valid")]),
                "external_assets_included": False,
            },
            "current_state": state,
            "latest_experiment": experiment_events[-1] if experiment_events else None,
            "last_result": run_events[-1] if run_events else None,
            "latest_decision": decisions[-1].stem if decisions else None,
            "next_action": state.get("Next Action"),
            "registry_summary": knowledge.summary(),
            "knowledge_navigation": knowledge.check(),
            "evidence_graph": __import__(
                "researchflow.evidence_graph", fromlist=["EvidenceGraphStore"]
            ).EvidenceGraphStore(self).summary(),
            "corpus_gap": {
                **__import__("researchflow.corpus_gap", fromlist=["CorpusStore"]).CorpusStore(self).summary(),
                **__import__("researchflow.corpus_gap", fromlist=["GapStore"]).GapStore(self).summary(),
            },
        }
        if verbose:
            result["registry_entries"] = knowledge.inventory()
            result["artifact_verification"] = __import__("researchflow.artifact", fromlist=["ArtifactStore"]).ArtifactStore(self).verify()
        return result

    @property
    def evidence(self):
        from .evidence import EvidenceStore
        return EvidenceStore(self)

    @property
    def experiments(self):
        from .experiments import ExperimentStore
        return ExperimentStore(self)
