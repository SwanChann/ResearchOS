from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import config_path, load_config, research_home, save_config
from .errors import ResearchFlowError
from .experiments import ExperimentStore, experiment_repo, preflight
from .ids import allocate_id
from .io import append_jsonl, atomic_text, read_jsonl, read_yaml, utc_now, write_yaml
from .project import ResearchProject, update_current_state
from .runs import run_path
from .schema import validate_record


_REMOTE_RUNNER = r'''#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def append_event(path: Path, state: str, job: dict) -> None:
    event = {
        "event": state,
        "at": now(),
        "run_id": job.get("run_id"),
        "experiment": job.get("experiment"),
        "exit_code": job.get("exit_code"),
        "error": job.get("error"),
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    job_path = Path(sys.argv[1]).resolve()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    run_root = Path(job["remote_run_root"])
    worktree = Path(job["remote_worktree"])
    lock_dir = Path(job["remote_lock"])
    events_path = run_root / "events.jsonl"
    acquired = False
    append_event(events_path, job.get("state", "PREFLIGHT"), job)

    def update(state: str, **fields) -> None:
        job.update(fields)
        job["state"] = state
        job["updated_at"] = now()
        atomic_json(job_path, job)
        append_event(events_path, state, job)

    try:
        if int(job["gpu_count"]) == 1:
            update("GPU_WAIT")
            lock_dir.parent.mkdir(parents=True, exist_ok=True)
            try:
                lock_dir.mkdir(parents=False)
            except FileExistsError:
                update("FAILED", ended_at=now(), exit_code=None, error="remote GPU lock is active")
                return 75
            acquired = True
            atomic_json(lock_dir / "owner.json", {
                "run_id": job["run_id"],
                "experiment": job["experiment"],
                "started_at": now(),
                "pid": os.getpid(),
                "host": socket.gethostname(),
            })

        environment = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "host": socket.gethostname(),
            "gpu": [],
        }
        if int(job["gpu_count"]) == 1 and shutil.which("nvidia-smi"):
            gpu = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,name,memory.total,driver_version", "--format=csv,noheader"],
                capture_output=True,
                text=True,
            )
            if gpu.returncode == 0:
                environment["gpu"] = gpu.stdout.strip().splitlines()
        atomic_json(run_root / "environment.json", environment)

        update("RUNNING", started_at=now(), error=None)
        env = os.environ.copy()
        env["RF_RUN_DIR"] = str(run_root)
        env["CUDA_VISIBLE_DEVICES"] = "0" if int(job["gpu_count"]) == 1 else ""
        log_path = run_root / "run.log"
        with log_path.open("w", encoding="utf-8", newline="\n") as log:
            log.write(f"# {'TEST / MOCK' if job['test_only'] else 'FORMAL REMOTE RUN'}\n\n")
            log.write(f"$ {job['command']}\n\n")
            log.flush()
            result = subprocess.run(
                job["command"],
                cwd=worktree,
                shell=True,
                executable="/bin/sh",
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )

        metrics_path = run_root / "metrics.json"
        metrics_valid = False
        metric_error = None
        if metrics_path.is_file():
            try:
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                metrics_valid = isinstance(metrics, dict)
                if not metrics_valid:
                    metric_error = "metrics.json must contain a JSON object"
            except json.JSONDecodeError as exc:
                metric_error = f"invalid metrics.json: {exc.msg}"
        else:
            metric_error = "metrics.json was not produced"

        succeeded = result.returncode == 0 and metrics_valid
        update(
            "SUCCEEDED" if succeeded else "FAILED",
            ended_at=now(),
            exit_code=result.returncode,
            metrics_valid=metrics_valid,
            error=None if succeeded else metric_error or f"command exited {result.returncode}",
        )
        return 0 if succeeded else 1
    except Exception as exc:
        update("FAILED", ended_at=now(), exit_code=None, error=f"runner error: {type(exc).__name__}: {exc}")
        return 1
    finally:
        if acquired:
            owner = lock_dir / "owner.json"
            try:
                current = json.loads(owner.read_text(encoding="utf-8"))
            except Exception:
                current = {}
            if current.get("run_id") == job.get("run_id"):
                owner.unlink(missing_ok=True)
                try:
                    lock_dir.rmdir()
                except OSError:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
'''


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
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return {"machine": name, "reachable": False, "stdout": "", "stderr": "SSH probe timed out after 15 seconds", "probed": True}
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


def _remote_paths(machine: dict[str, Any], project_id: str, run_id: str) -> dict[str, str]:
    root = machine["workspace_root"].rstrip("/")
    return {
        "remote_repo": f"{root}/repos/{project_id}",
        "remote_worktree": f"{root}/worktrees/{project_id}/{run_id}",
        "remote_run_root": f"{root}/runs/{run_id}",
        "remote_lock": f"{root}/locks/gpu0.lock",
    }


def _validate_run_id(run_id: str) -> None:
    if not re.fullmatch(r"RUN-[0-9]{6}", run_id):
        raise ResearchFlowError(f"Invalid remote run ID: {run_id}")


def _ssh(machine: dict[str, Any], remote_command: str, *, input_text: str | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", machine["host"], remote_command],
            input=input_text.encode("utf-8") if input_text is not None else None,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ResearchFlowError(f"SSH command timed out after {timeout} seconds on {machine['host']}.") from exc


def _bootstrap_script(job: dict[str, Any], card_text: str) -> str:
    encoded_job = base64.b64encode((json.dumps(job, indent=2, ensure_ascii=False) + "\n").encode()).decode()
    encoded_runner = base64.b64encode(_REMOTE_RUNNER.encode()).decode()
    encoded_card = base64.b64encode(card_text.encode()).decode()
    return f'''set -eu
umask 077
repo=$1
worktree=$2
run_root=$3
commit=$4
test -d "$repo/.git"
if ! git -C "$repo" cat-file -e "$commit^{{commit}}" 2>/dev/null; then
  git -C "$repo" fetch --all --prune
fi
git -C "$repo" cat-file -e "$commit^{{commit}}"
test ! -e "$worktree"
mkdir -p "$(dirname "$worktree")" "$run_root"
git -C "$repo" worktree add --detach "$worktree" "$commit"
test -z "$(git -C "$worktree" status --porcelain)"
printf %s {shlex.quote(encoded_job)} | base64 -d > "$run_root/job.json"
printf %s {shlex.quote(encoded_runner)} | base64 -d > "$run_root/remote_runner.py"
printf %s {shlex.quote(encoded_card)} | base64 -d > "$run_root/experiment-card.yaml"
chmod 700 "$run_root/remote_runner.py"
nohup python3 "$run_root/remote_runner.py" "$run_root/job.json" > "$run_root/supervisor.log" 2>&1 </dev/null &
echo $!
'''


def _launch_remote(machine: dict[str, Any], job: dict[str, Any], card_text: str) -> int:
    args = [job["remote_repo"], job["remote_worktree"], job["remote_run_root"], job["commit"]]
    remote_command = "sh -s -- " + " ".join(shlex.quote(value) for value in args)
    result = _ssh(machine, remote_command, input_text=_bootstrap_script(job, card_text), timeout=120)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip() or result.stdout.decode("utf-8", errors="replace").strip() or f"exit {result.returncode}"
        raise ResearchFlowError(f"Remote preflight/submit failed on {machine['host']}: {detail}")
    try:
        stdout = result.stdout.decode("utf-8", errors="replace").strip()
        return int(stdout.splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise ResearchFlowError(f"Remote submit did not return a runner PID: {stdout or '<empty>'}") from exc


def _hash_file(path: Path | None) -> str | None:
    if not path or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _registered_run_count(project: ResearchProject, experiment_id: str, level: str) -> int:
    return sum(
        1 for item in read_jsonl(project.root / "runs" / "registry.jsonl")
        if item.get("event") == "registered"
        and item.get("experiment") == experiment_id
        and item.get("level") == level
    )


def remote_submit(
    machine_name: str,
    project_id: str,
    experiment_id: str,
    level: str,
    *,
    dry_run: bool = False,
    confirmed: bool = False,
) -> dict[str, Any]:
    machine = get_machine(machine_name)
    if machine["type"] != "ssh":
        raise ResearchFlowError(f"Remote submit requires an SSH machine, got {machine['type']}: {machine_name}")
    project = ResearchProject.open(project_id)
    store = ExperimentStore(project)
    card = store.get(experiment_id)
    if card["compute"]["machine"] != machine_name:
        raise ResearchFlowError(
            f"Experiment {experiment_id} targets machine {card['compute']['machine']}, not {machine_name}. "
            f"Edit the card before submitting."
        )
    if level == "full" and (card["approval"]["full"] != "approved" or not confirmed):
        raise ResearchFlowError("A remote full run requires approval.full=approved and explicit --yes confirmation.")
    maximum = card["budget"][level].get("max_runs")
    if maximum is not None and _registered_run_count(project, experiment_id, level) >= maximum:
        raise ResearchFlowError(f"Experiment {experiment_id} exhausted {level} budget: max_runs={maximum}.")
    checks = preflight(project, experiment_id, level, run_tests=not dry_run)
    failures = [check for check in checks if not check.ok]
    if failures:
        detail = "\n".join(f"- {check.name}: {check.detail}" for check in failures)
        raise ResearchFlowError(f"Experiment {experiment_id} cannot enter remote {level.upper()}.\nPreflight failed:\n{detail}")

    commit = card.get("experiment_commit") or card["baseline"]["commit"]
    run_id = "RUN-DRYRUN" if dry_run else allocate_id(research_home(), "RUN")
    paths = _remote_paths(machine, project_id, run_id)
    job = {
        "run_id": run_id,
        "project": project_id,
        "experiment": experiment_id,
        "level": level,
        "state": "PREFLIGHT",
        "command": card["run"]["command"],
        "commit": commit,
        "gpu_count": card["compute"]["gpu_count"],
        "test_only": card["test_only"],
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "started_at": None,
        "ended_at": None,
        "exit_code": None,
        "error": None,
        **paths,
    }
    if dry_run:
        return {
            **job,
            "dry_run": True,
            "host": machine["host"],
            "actions": ["validate pinned commit", "create detached worktree", "launch background runner", "collect small text/JSON artifacts only"],
        }

    event = {
        "machine": machine_name,
        "run_id": run_id,
        "project": project_id,
        "experiment": experiment_id,
        "level": level,
        "at": utc_now(),
    }
    append_jsonl(jobs_path(), {"event": "QUEUED", **event})
    append_jsonl(jobs_path(), {"event": "PREFLIGHT", **event})
    try:
        pid = _launch_remote(machine, job, store.path(experiment_id).read_text(encoding="utf-8"))
    except Exception:
        append_jsonl(jobs_path(), {"event": "FAILED", **event, "at": utc_now(), "phase": "submit"})
        raise
    append_jsonl(jobs_path(), {"event": "SUBMITTED", **event, "at": utc_now(), "remote_pid": pid})
    if level == "smoke" and card["status"] == "IMPLEMENTED":
        store.transition(experiment_id, "SMOKE_TEST")
    elif level == "full" and card["status"] == "FULL_APPROVED":
        store.transition(experiment_id, "FULL_RUN")
    return {**job, "state": "SUBMITTED", "machine": machine_name, "host": machine["host"], "remote_pid": pid}


def _read_remote_small(machine: dict[str, Any], path: str, *, required: bool = True, max_bytes: int = 10 * 1024 * 1024) -> bytes | None:
    command = f"test -f {shlex.quote(path)} && head -c {max_bytes + 1} {shlex.quote(path)}"
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", machine["host"], command],
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise ResearchFlowError(f"Timed out reading remote artifact: {path}") from exc
    if result.returncode != 0:
        if required:
            raise ResearchFlowError(f"Remote artifact is missing or unreadable: {path}")
        return None
    if len(result.stdout) > max_bytes:
        raise ResearchFlowError(f"Remote artifact exceeds {max_bytes} bytes and was not collected: {path}")
    return result.stdout


def remote_job_status(machine_name: str, run_id: str) -> dict[str, Any]:
    _validate_run_id(run_id)
    machine = get_machine(machine_name)
    if machine["type"] != "ssh":
        raise ResearchFlowError(f"Remote job status requires an SSH machine: {machine_name}")
    root = machine["workspace_root"].rstrip("/")
    payload = _read_remote_small(machine, f"{root}/runs/{run_id}/job.json")
    try:
        job = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchFlowError(f"Remote job metadata is invalid for {run_id}: {exc}") from exc
    if job.get("run_id") != run_id:
        raise ResearchFlowError(f"Remote job ID mismatch: expected {run_id}, got {job.get('run_id')}")
    append_jsonl(jobs_path(), {
        "event": job.get("state", "UNKNOWN"),
        "machine": machine_name,
        "run_id": run_id,
        "project": job.get("project"),
        "experiment": job.get("experiment"),
        "at": utc_now(),
    })
    return {"machine": machine_name, **job}


def _decode_json_artifact(payload: bytes, name: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchFlowError(f"Collected {name} is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ResearchFlowError(f"Collected {name} must contain a JSON object.")
    return value


def remote_collect(machine_name: str, project_id: str, run_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    _validate_run_id(run_id)
    machine = get_machine(machine_name)
    if machine["type"] != "ssh":
        raise ResearchFlowError(f"Remote collect requires an SSH machine: {machine_name}")
    project = ResearchProject.open(project_id)
    status = remote_job_status(machine_name, run_id)
    if status.get("project") != project_id:
        raise ResearchFlowError(f"Remote job {run_id} belongs to project {status.get('project')}, not {project_id}.")
    if status.get("state") not in {"SUCCEEDED", "FAILED"}:
        raise ResearchFlowError(f"Remote job {run_id} is {status.get('state')}; collect only after SUCCEEDED or FAILED.")
    target = run_path(project, run_id)
    if target.exists():
        raise ResearchFlowError(f"Run is already collected locally: {run_id} ({target})")
    if dry_run:
        return {
            "run_id": run_id,
            "state": status["state"],
            "dry_run": True,
            "collect": ["job.json", "events.jsonl", "remote_runner.py", "run.log", "environment.json", "metrics.json when present", "experiment-card.yaml"],
            "never_collect": ["datasets", "checkpoints", "videos", "remote worktree"],
        }

    remote_root = status["remote_run_root"]
    payloads: dict[str, bytes] = {
        "job.json": _read_remote_small(machine, f"{remote_root}/job.json"),
        "events.jsonl": _read_remote_small(machine, f"{remote_root}/events.jsonl"),
        "remote_runner.py": _read_remote_small(machine, f"{remote_root}/remote_runner.py"),
        "run.log": _read_remote_small(machine, f"{remote_root}/run.log"),
        "environment.json": _read_remote_small(machine, f"{remote_root}/environment.json"),
        "experiment-card.yaml": _read_remote_small(machine, f"{remote_root}/experiment-card.yaml"),
    }
    metrics_payload = _read_remote_small(machine, f"{remote_root}/metrics.json", required=False)
    supervisor = _read_remote_small(machine, f"{remote_root}/supervisor.log", required=False)
    if metrics_payload is not None:
        payloads["metrics.json"] = metrics_payload
    if supervisor is not None:
        payloads["supervisor.log"] = supervisor

    job = _decode_json_artifact(payloads["job.json"], "job.json")
    environment = _decode_json_artifact(payloads["environment.json"], "environment.json")
    metrics = _decode_json_artifact(metrics_payload, "metrics.json") if metrics_payload is not None else {}
    store = ExperimentStore(project)
    card = store.get(job["experiment"])
    config_value = card["baseline"].get("config")
    repo = experiment_repo(project, job["experiment"])
    config_path_value = repo / config_value if config_value else None
    final_paths = {
        name: (Path("runs") / run_id / name).as_posix()
        for name in payloads
    }
    record: dict[str, Any] = {
        "id": run_id,
        "experiment": job["experiment"],
        "level": job["level"],
        "status": "succeeded" if job["state"] == "SUCCEEDED" else "failed",
        "started_at": job.get("started_at") or job["created_at"],
        "ended_at": job.get("ended_at") or job["updated_at"],
        "command": job["command"],
        "git": {"repo": job["remote_worktree"], "branch": None, "commit": job["commit"], "dirty": False, "diff_hash": None},
        "config": {"path": config_value, "hash": _hash_file(config_path_value)},
        "dataset": {"id": None, "manifest_hash": None},
        "environment": environment,
        "hardware": {
            "host": environment.get("host", machine["host"]),
            "gpu": environment.get("gpu", []),
            "gpu_count": job["gpu_count"],
        },
        "artifacts": {
            "log": final_paths["run.log"],
            "metrics": final_paths.get("metrics.json"),
            "environment": final_paths["environment.json"],
            "job": final_paths["job.json"],
            "job_events": final_paths["events.jsonl"],
            "runner": final_paths["remote_runner.py"],
            "runner_sha256": hashlib.sha256(payloads["remote_runner.py"]).hexdigest(),
            "experiment_card": final_paths["experiment-card.yaml"],
            "supervisor": final_paths.get("supervisor.log"),
            "checkpoints": [], "figures": [], "trajectories": [], "videos": [],
        },
        "metrics": metrics,
        "exit_code": job.get("exit_code"),
        "test_only": bool(job["test_only"]),
    }
    validate_record("run", record)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{run_id}.", dir=target.parent) as temporary:
        staging = Path(temporary)
        for name, payload in payloads.items():
            (staging / name).write_bytes(payload)
        write_yaml(staging / "run.yaml", record)
        os.replace(staging, target)
    event = {
        "id": run_id, "experiment": job["experiment"], "level": job["level"],
        "status": record["status"], "at": record["ended_at"], "test_only": record["test_only"],
    }
    append_jsonl(project.root / "runs" / "registry.jsonl", {"event": "registered", **event})
    append_jsonl(jobs_path(), {"event": "COLLECTED", "machine": machine_name, "run_id": run_id, "at": utc_now()})
    append_jsonl(jobs_path(), {"event": "REGISTERED", "machine": machine_name, "run_id": run_id, "at": utc_now()})
    store._event(card, "run_registered", latest_run=run_id)
    if job["level"] == "smoke":
        store.transition(job["experiment"], "PILOT" if record["status"] == "succeeded" else "FAILED_SMOKE")
    elif job["level"] == "pilot":
        store.transition(job["experiment"], "PILOT_PASS" if record["status"] == "succeeded" else "ANALYZE_FAILURE")
    elif job["level"] == "full":
        store.transition(job["experiment"], "ANALYZED" if record["status"] == "succeeded" else "ANALYZE_FAILURE")
    update_current_state(project, "Current Stage", f"Remote run {run_id} registered as {record['status']} ({job['level']}).")
    suffix = " This TEST / MOCK run is pipeline evidence only." if record["test_only"] else ""
    update_current_state(project, "Next Action", f"Inspect {run_id} artifacts and uncertainty before recording a research observation.{suffix}")
    return record


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
    submit = actions.add_parser("submit")
    submit.add_argument("name")
    submit.add_argument("--project-id", required=True)
    submit.add_argument("--experiment", required=True)
    submit.add_argument("--level", choices=("smoke", "pilot", "full"), default="smoke")
    submit.add_argument("--dry-run", action="store_true")
    submit.add_argument("--yes", action="store_true")
    job = actions.add_parser("job")
    job.add_argument("name")
    job.add_argument("run_id")
    collect = actions.add_parser("collect")
    collect.add_argument("name")
    collect.add_argument("run_id")
    collect.add_argument("--project-id", required=True)
    collect.add_argument("--dry-run", action="store_true")


def execute_compute_command(args: argparse.Namespace) -> int:
    from .cli import dump
    if args.action == "add":
        dump(add_machine(args.name, args.type, args.host, args.workspace_root, args.gpu_count))
    elif args.action == "list":
        dump(load_config().get("machines", {}))
    elif args.action == "probe":
        result = probe_machine(args.name, args.dry_run)
        dump(result)
        if result.get("reachable") is False:
            return 1
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
    elif args.action == "submit":
        dump(remote_submit(args.name, args.project_id, args.experiment, args.level, dry_run=args.dry_run, confirmed=args.yes))
    elif args.action == "job":
        dump(remote_job_status(args.name, args.run_id))
    elif args.action == "collect":
        dump(remote_collect(args.name, args.project_id, args.run_id, dry_run=args.dry_run))
    return 0
