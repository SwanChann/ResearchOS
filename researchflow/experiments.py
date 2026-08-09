from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import research_home
from .errors import ResearchFlowError
from .gitops import changed_paths, check_scope, commit_exists, create_worktree, dirty_paths, head, require_git_repo
from .ids import allocate_id
from .io import append_jsonl, read_jsonl, read_markdown_record, read_yaml, utc_now, write_yaml
from .project import ResearchProject
from .schema import validate_record

TRANSITIONS = {
    "DRAFT": {"EVIDENCE_READY"},
    "EVIDENCE_READY": {"HYPOTHESIS_APPROVED"},
    "HYPOTHESIS_APPROVED": {"IMPLEMENTED"},
    "IMPLEMENTED": {"SMOKE_TEST"},
    "SMOKE_TEST": {"FAILED_SMOKE", "PILOT"},
    "FAILED_SMOKE": {"IMPLEMENTED"},
    "PILOT": {"ANALYZE_FAILURE", "PILOT_PASS"},
    "ANALYZE_FAILURE": {"IMPLEMENTED", "ANALYZED"},
    "PILOT_PASS": {"FULL_APPROVED"},
    "FULL_APPROVED": {"FULL_RUN"},
    "FULL_RUN": {"ANALYZED"},
    "ANALYZED": {"DECIDED"},
    "DECIDED": {"ACCEPTED", "REJECTED", "INCONCLUSIVE", "FOLLOW_UP"},
    "ACCEPTED": set(), "REJECTED": set(), "INCONCLUSIVE": set(), "FOLLOW_UP": set(),
}


def worktree_path(project: ResearchProject, experiment_id: str) -> Path:
    return research_home() / "worktrees" / project.data["id"] / experiment_id


def experiment_repo(project: ResearchProject, experiment_id: str) -> Path:
    worktree = worktree_path(project, experiment_id)
    return worktree if worktree.is_dir() else project.repo


@dataclass
class PreflightCheck:
    name: str
    ok: bool
    detail: str


class ExperimentStore:
    def __init__(self, project: ResearchProject):
        self.project = project

    def path(self, experiment_id: str) -> Path:
        return self.project.root / "experiments" / "cards" / f"{experiment_id}.yaml"

    def get(self, experiment_id: str) -> dict[str, Any]:
        path = self.path(experiment_id)
        if not path.exists():
            raise ResearchFlowError(f"Experiment card not found: {experiment_id}")
        card = read_yaml(path)
        validate_record("experiment", card)
        return card

    def create(self, hypothesis: str, title: str, question: str, command: str, allowed_paths: list[str], frozen_paths: list[str], primary: str, secondary: list[str], guardrails: dict[str, Any], stop_conditions: list[str], config_path: str | None = None) -> str:
        hypothesis_path = self.project.root / "memory" / "hypotheses" / f"{hypothesis}.md"
        if not hypothesis_path.exists():
            raise ResearchFlowError(f"Hypothesis does not exist: {hypothesis}")
        hypothesis_metadata, _ = read_markdown_record(hypothesis_path)
        require_git_repo(self.project.repo)
        experiment_id = allocate_id(research_home(), "EXP")
        now = utc_now()
        card = {
            "id": experiment_id, "title": title, "status": "DRAFT", "question": question,
            "hypothesis": {"id": hypothesis},
            "evidence": {
                "papers": hypothesis_metadata.get("based_on", {}).get("papers", []),
                "repos": [],
                "observations": hypothesis_metadata.get("based_on", {}).get("observations", []),
            },
            "baseline": {"repo": str(self.project.repo), "commit": head(self.project.repo), "config": config_path},
            "change": {"summary": "Not yet implemented."},
            "scope": {"allowed_paths": allowed_paths, "frozen_paths": frozen_paths},
            "metrics": {"primary": primary, "secondary": secondary, "guardrails": guardrails},
            "budget": {"smoke": {"max_runs": 1}, "pilot": {"max_runs": 3}, "full": {"max_runs": 10, "max_gpu_hours": 8}},
            "stop_conditions": stop_conditions,
            "compute": {"machine": "local", "gpu_count": 0},
            "approval": {"implementation": "auto", "pilot": "auto", "full": "human"},
            "run": {"command": command, "required_tests": []},
            "experiment_commit": None, "created": now, "updated": now,
        }
        validate_record("experiment", card)
        write_yaml(self.path(experiment_id), card)
        self._event(card, "created")
        return experiment_id

    def _event(self, card: dict[str, Any], event: str, latest_run: str | None = None) -> None:
        append_jsonl(self.project.root / "experiments" / "registry.jsonl", {
            "event": event, "id": card["id"], "status": card["status"],
            "hypothesis": card["hypothesis"]["id"],
            "card": self.path(card["id"]).relative_to(self.project.root).as_posix(),
            "baseline_commit": card["baseline"]["commit"],
            "experiment_commit": card.get("experiment_commit"), "latest_run": latest_run,
            "created": card["created"], "updated": card["updated"],
        })

    def transition(self, experiment_id: str, target: str) -> dict[str, Any]:
        card = self.get(experiment_id)
        source, target = card["status"], target.upper()
        if target not in TRANSITIONS.get(source, set()):
            allowed = ", ".join(sorted(TRANSITIONS.get(source, set()))) or "none"
            raise ResearchFlowError(f"Experiment {experiment_id} cannot transition {source} -> {target}. Allowed next states: {allowed}.")
        if target == "EVIDENCE_READY" and not any(card["evidence"].values()):
            raise ResearchFlowError(f"Experiment {experiment_id} cannot enter EVIDENCE_READY: no linked paper, repository, or observation evidence.")
        if target == "FULL_APPROVED" and card["approval"]["full"] != "approved":
            raise ResearchFlowError(f"Experiment {experiment_id} cannot enter FULL_APPROVED: approval.full is not approved.")
        card["status"] = target
        card["updated"] = utc_now()
        if target == "IMPLEMENTED":
            repo = experiment_repo(self.project, experiment_id)
            card["experiment_commit"] = head(repo)
        validate_record("experiment", card)
        write_yaml(self.path(experiment_id), card)
        self._event(card, "transition")
        return card

    def latest(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for event in read_jsonl(self.project.root / "experiments" / "registry.jsonl"):
            latest[event["id"]] = event
        return latest


def preflight(project: ResearchProject, experiment_id: str, level: str, allow_dirty: bool = False, run_tests: bool = True) -> list[PreflightCheck]:
    store = ExperimentStore(project)
    try:
        card = store.get(experiment_id)
        checks = [PreflightCheck("card schema", True, "valid")]
    except ResearchFlowError as exc:
        return [PreflightCheck("card schema", False, str(exc))]
    expected = {"smoke": {"IMPLEMENTED", "SMOKE_TEST", "FAILED_SMOKE"}, "pilot": {"PILOT"}, "full": {"FULL_APPROVED", "FULL_RUN"}}
    checks.append(PreflightCheck("state", card["status"] in expected[level], f"{card['status']} for {level}"))
    hypothesis = project.root / "memory" / "hypotheses" / f"{card['hypothesis']['id']}.md"
    checks.append(PreflightCheck("hypothesis", hypothesis.is_file(), card["hypothesis"]["id"]))
    repo = experiment_repo(project, experiment_id)
    try:
        require_git_repo(repo)
        checks.append(PreflightCheck("Git repository", True, str(repo)))
    except ResearchFlowError as exc:
        checks.append(PreflightCheck("Git repository", False, str(exc)))
        return checks
    baseline = card["baseline"].get("commit")
    checks.append(PreflightCheck("baseline commit", bool(baseline) and commit_exists(repo, baseline), str(baseline or "missing")))
    dirty = dirty_paths(repo)
    checks.append(PreflightCheck("clean worktree", not dirty or allow_dirty, "clean" if not dirty else f"dirty: {', '.join(dirty)}"))
    if baseline and commit_exists(repo, baseline):
        scope = check_scope(changed_paths(repo, baseline), card["scope"]["allowed_paths"], card["scope"]["frozen_paths"])
        checks.append(PreflightCheck("frozen paths", not scope.frozen_violations, ", ".join(scope.frozen_violations) or "none modified"))
        checks.append(PreflightCheck("allowed paths", not scope.outside_allowed, ", ".join(scope.outside_allowed) or "all changes allowed"))
    config = card["baseline"].get("config")
    checks.append(PreflightCheck("config", not config or (repo / config).is_file(), config or "not required"))
    checks.append(PreflightCheck("primary metric", bool(card["metrics"].get("primary")), str(card["metrics"].get("primary"))))
    checks.append(PreflightCheck("secondary metrics", bool(card["metrics"].get("secondary")), ", ".join(card["metrics"].get("secondary", [])) or "missing"))
    checks.append(PreflightCheck("guardrails", bool(card["metrics"].get("guardrails")), "defined" if card["metrics"].get("guardrails") else "missing"))
    checks.append(PreflightCheck("stop conditions", bool(card["stop_conditions"]), ", ".join(card["stop_conditions"]) or "missing"))
    checks.append(PreflightCheck("run command", bool(card["run"].get("command")), str(card["run"].get("command"))))
    checks.append(PreflightCheck("GPU requirement", card["compute"]["gpu_count"] <= 1, str(card["compute"]["gpu_count"])))
    if level == "full":
        checks.append(PreflightCheck("full approval", card["approval"]["full"] == "approved", card["approval"]["full"]))
    if run_tests:
        for command in card["run"].get("required_tests", []):
            result = subprocess.run(command, cwd=repo, shell=True, capture_output=True, text=True)
            checks.append(PreflightCheck(f"test: {command}", result.returncode == 0, f"exit {result.returncode}"))
    return checks


def add_experiment_parser(commands) -> None:
    command = commands.add_parser("experiment", help="design and execute bounded experiments")
    actions = command.add_subparsers(dest="action", required=True)
    new = actions.add_parser("new")
    new.add_argument("--hypothesis", required=True)
    new.add_argument("--title", required=True)
    new.add_argument("--question", required=True)
    new.add_argument("--command", required=True)
    new.add_argument("--allowed-paths", required=True)
    new.add_argument("--frozen-paths", default="")
    new.add_argument("--primary", required=True)
    new.add_argument("--secondary", required=True)
    new.add_argument("--guardrails", required=True, help="JSON object, e.g. {\"latency_pct\":10}")
    new.add_argument("--stop-conditions", required=True)
    new.add_argument("--config")
    show = actions.add_parser("show")
    show.add_argument("id")
    transition = actions.add_parser("transition")
    transition.add_argument("id")
    transition.add_argument("state")
    worktree = actions.add_parser("worktree")
    worktree.add_argument("id")
    worktree.add_argument("--dry-run", action="store_true")
    pre = actions.add_parser("preflight")
    pre.add_argument("id")
    pre.add_argument("--level", choices=("smoke", "pilot", "full"), default="smoke")
    pre.add_argument("--allow-dirty", action="store_true")
    pre.add_argument("--skip-tests", action="store_true")
    for level in ("smoke", "pilot", "full"):
        run = actions.add_parser(level)
        run.add_argument("id")
        run.add_argument("--allow-dirty", action="store_true")
        run.add_argument("--yes", action="store_true")


def execute_experiment_command(project: ResearchProject, args: argparse.Namespace) -> int:
    from .cli import csv, dump
    store = ExperimentStore(project)
    if args.action == "new":
        try:
            guardrails = json.loads(args.guardrails)
        except json.JSONDecodeError as exc:
            raise ResearchFlowError(f"--guardrails must be a JSON object: {exc.msg}") from exc
        if not isinstance(guardrails, dict):
            raise ResearchFlowError("--guardrails must be a JSON object.")
        print(store.create(args.hypothesis, args.title, args.question, args.command, csv(args.allowed_paths), csv(args.frozen_paths), args.primary, csv(args.secondary), guardrails, csv(args.stop_conditions), args.config))
    elif args.action == "show":
        dump(store.get(args.id))
    elif args.action == "transition":
        dump(store.transition(args.id, args.state))
    elif args.action == "worktree":
        card = store.get(args.id)
        print(create_worktree(project.repo, worktree_path(project, args.id), card["baseline"]["commit"], args.dry_run))
    elif args.action == "preflight":
        checks = preflight(project, args.id, args.level, args.allow_dirty, not args.skip_tests)
        for check in checks:
            print(f"{'OK' if check.ok else 'FAIL':4} {check.name}: {check.detail}")
        return 0 if all(check.ok for check in checks) else 1
    else:
        from .runs import execute_experiment_run
        return execute_experiment_run(project, args.id, args.action, args.allow_dirty, args.yes)
    return 0
