from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import research_home
from .errors import ResearchFlowError
from .experiments import ExperimentStore, experiment_repo, preflight
from .gitops import branch, diff_hash, dirty_paths, head
from .ids import allocate_id
from .io import append_jsonl, atomic_text, read_jsonl, read_yaml, utc_now, write_yaml
from .project import ResearchProject, update_current_state
from .schema import validate_record


def _hash_file(path: Path | None) -> str | None:
    if not path or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_path(project: ResearchProject, run_id: str) -> Path:
    return project.root / "runs" / run_id


def _run_count(project: ResearchProject, experiment_id: str, level: str) -> int:
    return sum(1 for item in read_jsonl(project.root / "runs" / "registry.jsonl") if item.get("experiment") == experiment_id and item.get("level") == level and item.get("event") == "registered")


def execute_local_run(project: ResearchProject, experiment_id: str, level: str, allow_dirty: bool = False) -> dict[str, Any]:
    store = ExperimentStore(project)
    card = store.get(experiment_id)
    maximum = card["budget"][level].get("max_runs")
    if maximum is not None and _run_count(project, experiment_id, level) >= maximum:
        raise ResearchFlowError(f"Experiment {experiment_id} exhausted {level} budget: max_runs={maximum}.")
    checks = preflight(project, experiment_id, level, allow_dirty=allow_dirty, run_tests=True)
    failures = [check for check in checks if not check.ok]
    if failures:
        detail = "\n".join(f"- {check.name}: {check.detail}" for check in failures)
        raise ResearchFlowError(f"Experiment {experiment_id} cannot enter {level.upper()}.\nPreflight failed:\n{detail}")
    repo = experiment_repo(project, experiment_id)
    run_id = allocate_id(research_home(), "RUN")
    root = run_path(project, run_id)
    root.mkdir(parents=True)
    log_path = root / "run.log"
    metrics_path = root / "metrics.json"
    environment_path = root / "environment.json"
    config_value = card["baseline"].get("config")
    config_file = repo / config_value if config_value else None
    dirty = bool(dirty_paths(repo))
    environment = {
        "python": sys.version.split()[0], "platform": platform.platform(),
        "cuda": os.environ.get("CUDA_VERSION"), "pytorch": None,
        "lockfile_hash": _hash_file(next((repo / name for name in ("uv.lock", "poetry.lock", "requirements.txt", "pyproject.toml") if (repo / name).is_file()), None)),
    }
    atomic_text(environment_path, json.dumps(environment, indent=2, ensure_ascii=False) + "\n")
    started = utc_now()
    record: dict[str, Any] = {
        "id": run_id, "experiment": experiment_id, "level": level, "status": "running",
        "started_at": started, "ended_at": None, "command": card["run"]["command"],
        "git": {"repo": str(repo), "branch": branch(repo), "commit": head(repo), "dirty": dirty, "diff_hash": diff_hash(repo) if dirty else None},
        "config": {"path": config_value, "hash": _hash_file(config_file)},
        "dataset": {"id": None, "manifest_hash": None},
        "environment": environment,
        "hardware": {"host": socket.gethostname(), "gpu": "not requested" if card["compute"]["gpu_count"] == 0 else "unprobed", "gpu_count": card["compute"]["gpu_count"]},
        "artifacts": {
            "log": log_path.relative_to(project.root).as_posix(),
            "metrics": metrics_path.relative_to(project.root).as_posix(),
            "environment": environment_path.relative_to(project.root).as_posix(),
            "checkpoints": [], "figures": [], "trajectories": [], "videos": [],
        },
        "metrics": {}, "exit_code": None, "test_only": card["test_only"],
    }
    validate_record("run", record)
    write_yaml(root / "run.yaml", record)
    append_jsonl(project.root / "runs" / "registry.jsonl", {"event": "started", "id": run_id, "experiment": experiment_id, "level": level, "status": "running", "at": started, "test_only": card["test_only"]})
    env = os.environ.copy()
    env["RF_RUN_DIR"] = str(root)
    result = subprocess.run(card["run"]["command"], cwd=repo, shell=True, capture_output=True, text=True, env=env)
    atomic_text(log_path, f"# {'TEST / MOCK' if card['test_only'] else 'FORMAL RUN'}\n\n$ {card['run']['command']}\n\n[stdout]\n{result.stdout}\n[stderr]\n{result.stderr}")
    metrics: dict[str, Any] = {}
    metric_error = None
    if metrics_path.is_file():
        try:
            loaded = json.loads(metrics_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                metric_error = "metrics.json must contain a JSON object"
            else:
                metrics = loaded
        except json.JSONDecodeError as exc:
            metric_error = f"invalid metrics.json: {exc.msg}"
    else:
        metric_error = "metrics.json was not produced"
    success = result.returncode == 0 and metric_error is None
    if metric_error:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n[ResearchFlow]\n{metric_error}\n")
    record.update({"status": "succeeded" if success else "failed", "ended_at": utc_now(), "metrics": metrics, "exit_code": result.returncode})
    validate_record("run", record)
    write_yaml(root / "run.yaml", record)
    append_jsonl(project.root / "runs" / "registry.jsonl", {"event": "registered", "id": run_id, "experiment": experiment_id, "level": level, "status": record["status"], "at": record["ended_at"], "test_only": card["test_only"]})
    store._event(card, "run_registered", latest_run=run_id)
    update_current_state(project, "Current Stage", f"Run {run_id} registered as {record['status']} ({level}).")
    update_current_state(project, "Next Action", f"Inspect {run_id} raw metrics, guardrails, failures, and uncertainty before recording an observation.")
    return record


def execute_experiment_run(project: ResearchProject, experiment_id: str, level: str, allow_dirty: bool, confirmed: bool) -> int:
    store = ExperimentStore(project)
    card = store.get(experiment_id)
    if level == "full" and not confirmed:
        raise ResearchFlowError("A full run requires explicit --yes confirmation after human approval.")
    if level == "smoke" and card["status"] == "IMPLEMENTED":
        store.transition(experiment_id, "SMOKE_TEST")
    elif level == "full" and card["status"] == "FULL_APPROVED":
        store.transition(experiment_id, "FULL_RUN")
    record = execute_local_run(project, experiment_id, level, allow_dirty)
    if level == "smoke":
        store.transition(experiment_id, "PILOT" if record["status"] == "succeeded" else "FAILED_SMOKE")
    elif level == "pilot":
        store.transition(experiment_id, "PILOT_PASS" if record["status"] == "succeeded" else "ANALYZE_FAILURE")
    elif level == "full":
        store.transition(experiment_id, "ANALYZED" if record["status"] == "succeeded" else "ANALYZE_FAILURE")
    print(f"{record['id']} {record['status']} ({level})")
    return 0 if record["status"] == "succeeded" else 1


def get_run(project: ResearchProject, run_id: str) -> dict[str, Any]:
    path = run_path(project, run_id) / "run.yaml"
    if not path.is_file():
        raise ResearchFlowError(f"Run not found: {run_id}")
    data = read_yaml(path)
    validate_record("run", data)
    return data


def add_run_parser(commands) -> None:
    command = commands.add_parser("run", help="inspect registered runs")
    actions = command.add_subparsers(dest="action", required=True)
    for action in ("show", "logs", "artifacts"):
        child = actions.add_parser(action)
        child.add_argument("id")


def execute_run_command(project: ResearchProject, args: argparse.Namespace) -> int:
    from .cli import dump
    record = get_run(project, args.id)
    if args.action == "show":
        dump(record)
    elif args.action == "logs":
        print((project.root / record["artifacts"]["log"]).read_text(encoding="utf-8"))
    else:
        dump(record["artifacts"])
    return 0
