from __future__ import annotations

import argparse
import os
import platform
import shlex
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import config_path, load_config, save_config
from .errors import ResearchFlowError
from .io import append_jsonl, read_jsonl, read_yaml, utc_now, write_yaml


def add_machine(name: str, machine_type: str, host: str | None, workspace_root: str, gpu_count: int = 1) -> dict[str, Any]:
    if not name or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in name):
        raise ResearchFlowError("Machine name may contain only letters, numbers, '-' and '_'.")
    if machine_type == "ssh" and not host:
        raise ResearchFlowError("SSH machines require --host (an SSH config alias is recommended).")
    if gpu_count not in (0, 1):
        raise ResearchFlowError("V0.1 supports gpu_count 0 or 1 only; use one active heavy job per machine.")
    config = load_config()
    if name in config["machines"]:
        raise ResearchFlowError(f"Machine already exists: {name}")
    machine = {
        "type": machine_type,
        "host": host or "localhost",
        "workspace_root": workspace_root,
        "capabilities": {"gpu_count": gpu_count},
    }
    config["machines"][name] = machine
    save_config(config)
    return machine


def get_machine(name: str) -> dict[str, Any]:
    machines = load_config().get("machines", {})
    if name not in machines:
        raise ResearchFlowError(f"Unknown machine: {name}. Run: rf compute list")
    return machines[name]


def probe_machine(name: str, dry_run: bool = False) -> dict[str, Any]:
    machine = get_machine(name)
    if machine["type"] == "local":
        if dry_run:
            return {"machine": name, "reachable": None, "dry_run": "local platform/Git/nvidia-smi probe", "probed": False}
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True) if shutil.which("nvidia-smi") else None
        return {
            "machine": name, "reachable": True, "host": socket.gethostname(),
            "platform": platform.platform(), "git": shutil.which("git"),
            "gpu": gpu.stdout.strip().splitlines() if gpu and gpu.returncode == 0 else [],
            "probed": True,
        }
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", machine["host"], "uname -s; python3 --version; git --version; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader"]
    if dry_run:
        return {"machine": name, "reachable": None, "dry_run": subprocess.list2cmdline(command), "probed": False}
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    return {"machine": name, "reachable": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip(), "probed": True}


def lock_dir() -> Path:
    return config_path().parent / "locks"


def lock_path(machine: str) -> Path:
    return lock_dir() / f"{machine}-gpu0.lock"


def jobs_path() -> Path:
    return config_path().parent / "jobs.jsonl"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def lock_status(machine: str, stale_after_hours: float = 24.0) -> dict[str, Any]:
    path = lock_path(machine)
    if not path.exists():
        return {"machine": machine, "locked": False, "stale": False}
    try:
        data = read_yaml(path)
    except ResearchFlowError as exc:
        return {"machine": machine, "locked": True, "stale": True, "reason": f"invalid lock: {exc}"}
    stale = False
    reason = None
    started = data.get("started_at")
    if data.get("host") == socket.gethostname() and isinstance(data.get("pid"), int) and not _pid_alive(data["pid"]):
        stale, reason = True, "owner PID is not alive"
    if started:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(started)).total_seconds() / 3600
            if age > stale_after_hours:
                stale, reason = True, f"lock age {age:.1f}h exceeds {stale_after_hours:.1f}h"
        except ValueError:
            stale, reason = True, "invalid started_at"
    return {"machine": machine, "locked": True, "stale": stale, "reason": reason, **data}


def acquire_gpu_lock(machine: str, experiment: str, job_id: str, owner: str | None = None) -> dict[str, Any]:
    get_machine(machine)
    path = lock_path(machine)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "machine": machine, "gpu": 0, "pid": os.getpid(), "host": socket.gethostname(),
        "job_id": job_id, "owner": owner or os.environ.get("USERNAME") or os.environ.get("USER") or "unknown",
        "experiment": experiment, "started_at": utc_now(),
    }
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(descriptor)
    except FileExistsError as exc:
        status = lock_status(machine)
        hint = "The lock is stale; run `rf compute unlock NAME --force --yes` after verifying no GPU process is active." if status.get("stale") else "Wait for the active job or inspect `rf compute status`."
        raise ResearchFlowError(f"GPU {machine}:0 is already locked by {status.get('job_id', 'unknown')}. {hint}") from exc
    try:
        write_yaml(path, data)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    append_jsonl(jobs_path(), {"event": "QUEUED", **data})
    append_jsonl(jobs_path(), {"event": "PREFLIGHT", **data, "at": utc_now()})
    append_jsonl(jobs_path(), {"event": "GPU_WAIT", **data, "at": utc_now()})
    append_jsonl(jobs_path(), {"event": "RUNNING", **data, "at": utc_now()})
    return data


def release_gpu_lock(machine: str, force: bool = False, confirmed: bool = False) -> None:
    status = lock_status(machine)
    if not status["locked"]:
        raise ResearchFlowError(f"GPU {machine}:0 is not locked.")
    if force and not confirmed:
        raise ResearchFlowError("Force-unlock requires explicit --yes after checking the GPU process on the target machine.")
    if not force and not status["stale"]:
        raise ResearchFlowError(f"GPU {machine}:0 lock is active. Refusing to unlock; use --force --yes only after external verification.")
    lock_path(machine).unlink()
    append_jsonl(jobs_path(), {"event": "CANCELLED" if force else "STALE_UNLOCKED", "machine": machine, "job_id": status.get("job_id"), "at": utc_now()})


def remote_plan(machine_name: str, project_id: str, experiment_id: str, commit: str, command: str) -> dict[str, Any]:
    machine = get_machine(machine_name)
    if machine["type"] != "ssh":
        raise ResearchFlowError(f"Remote plan requires an SSH machine, got {machine['type']}: {machine_name}")
    root = machine["workspace_root"].rstrip("/")
    repo = f"{root}/repos/{project_id}"
    worktree = f"{root}/worktrees/{experiment_id}"
    run_root = f"{root}/runs/{experiment_id}"
    q = shlex.quote
    steps = [
        f"test -d {q(repo + '/.git')}",
        f"git -C {q(repo)} fetch --all --prune",
        f"git -C {q(repo)} cat-file -e {q(commit + '^{commit}')}",
        f"mkdir -p {q(root + '/worktrees')} {q(run_root)}",
        f"test -d {q(worktree)} || git -C {q(repo)} worktree add --detach {q(worktree)} {q(commit)}",
        f"test -z \"$(git -C {q(worktree)} status --porcelain)\"",
        f"cd {q(worktree)} && RF_RUN_DIR={q(run_root)} sh -lc {q(command)}",
    ]
    return {
        "machine": machine_name, "host": machine["host"], "project": project_id,
        "experiment": experiment_id, "commit": commit,
        "remote_repo": repo, "remote_worktree": worktree, "remote_run_root": run_root,
        "sync": ["commit", "experiment card", "config", "small metadata"],
        "never_auto_sync": ["datasets", "large checkpoints", "whole repository"],
        "job_states": ["QUEUED", "PREFLIGHT", "GPU_WAIT", "RUNNING", "SUCCEEDED|FAILED|CANCELLED", "COLLECTED", "REGISTERED"],
        "ssh_command": ["ssh", machine["host"], "set -eu; " + "; ".join(steps)],
    }


def add_compute_parser(commands) -> None:
    command = commands.add_parser("compute", help="manage local and SSH compute targets")
    actions = command.add_subparsers(dest="action", required=True)
    add = actions.add_parser("add")
    add.add_argument("name")
    add.add_argument("--type", choices=("local", "ssh"), required=True)
    add.add_argument("--host")
    add.add_argument("--workspace-root", required=True)
    add.add_argument("--gpu-count", type=int, default=1)
    actions.add_parser("list")
    probe = actions.add_parser("probe")
    probe.add_argument("name")
    probe.add_argument("--dry-run", action="store_true")
    status = actions.add_parser("status")
    status.add_argument("name", nargs="?")
    actions.add_parser("jobs")
    lock = actions.add_parser("lock")
    lock.add_argument("name")
    lock.add_argument("--experiment", required=True)
    lock.add_argument("--job-id", required=True)
    lock.add_argument("--owner")
    unlock = actions.add_parser("unlock")
    unlock.add_argument("name")
    unlock.add_argument("--force", action="store_true")
    unlock.add_argument("--yes", action="store_true")
    plan = actions.add_parser("plan")
    plan.add_argument("name")
    plan.add_argument("--project-id", required=True)
    plan.add_argument("--experiment", required=True)
    plan.add_argument("--commit", required=True)
    plan.add_argument("--command", required=True)


def execute_compute_command(args: argparse.Namespace) -> int:
    from .cli import dump
    if args.action == "add":
        dump(add_machine(args.name, args.type, args.host, args.workspace_root, args.gpu_count))
    elif args.action == "list":
        dump(load_config().get("machines", {}))
    elif args.action == "probe":
        dump(probe_machine(args.name, args.dry_run))
    elif args.action == "status":
        names = [args.name] if args.name else list(load_config().get("machines", {}))
        dump([lock_status(name) for name in names])
    elif args.action == "jobs":
        dump(read_jsonl(jobs_path()))
    elif args.action == "lock":
        dump(acquire_gpu_lock(args.name, args.experiment, args.job_id, args.owner))
    elif args.action == "unlock":
        release_gpu_lock(args.name, args.force, args.yes)
        print(f"Unlocked {args.name}:0")
    elif args.action == "plan":
        dump(remote_plan(args.name, args.project_id, args.experiment, args.commit, args.command))
    return 0
