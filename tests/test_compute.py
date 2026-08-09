import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from researchflow.compute import (
    acquire_gpu_lock,
    add_machine,
    jobs_path,
    lock_path,
    lock_status,
    release_gpu_lock,
    remote_collect,
    remote_plan,
    remote_submit,
)
from researchflow.errors import ResearchFlowError
from researchflow.experiments import worktree_path
from researchflow.gitops import create_worktree
from researchflow.io import read_jsonl, write_yaml
from researchflow.project import ResearchProject, add_project
from researchflow.records import add_hypothesis, add_observation


def _commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", message], check=True, capture_output=True)


def _remote_test_experiment(rf_env):
    fixture = Path(__file__).parents[1] / "examples" / "toy-research" / "baseline.py"
    shutil.copy2(fixture, rf_env["repo"] / "baseline.py")
    subprocess.run(["git", "init", "-b", "main", str(rf_env["repo"])], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(rf_env["repo"]), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(rf_env["repo"]), "config", "user.email", "test@example.invalid"], check=True)
    _commit(rf_env["repo"], "TEST baseline")
    add_project("toy", rf_env["repo"], "Toy Remote (TEST)")
    project = ResearchProject.open("toy")
    observation = add_observation(project, "TEST baseline", "TEST / MOCK fixture only.")
    hypothesis = add_hypothesis(
        project,
        "TEST remote execution",
        "The remote fixture writes deterministic metrics.",
        [observation],
        falsification="The fixture does not write score 6.",
    )
    experiment = project.experiments.create(
        hypothesis,
        "TEST remote fixture",
        "Does the remote pipeline preserve deterministic output?",
        "python baseline.py --input 3",
        ["baseline.py"],
        [],
        "score",
        ["exit_code"],
        {"runtime_seconds_max": 10},
        ["nonzero_exit", "max_runs"],
        test_only=True,
    )
    card = project.experiments.get(experiment)
    target = worktree_path(project, experiment)
    create_worktree(project.repo, target, card["baseline"]["commit"])
    source = (target / "baseline.py").read_text(encoding="utf-8").replace("MULTIPLIER = 1", "MULTIPLIER = 2")
    (target / "baseline.py").write_text(source, encoding="utf-8")
    subprocess.run(["git", "-C", str(target), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(target), "config", "user.email", "test@example.invalid"], check=True)
    _commit(target, "TEST remote change")
    for state in ("EVIDENCE_READY", "HYPOTHESIS_APPROVED", "IMPLEMENTED"):
        project.experiments.transition(experiment, state)
    card = project.experiments.get(experiment)
    card["compute"] = {"machine": "server4090", "gpu_count": 0}
    write_yaml(project.experiments.path(experiment), card)
    add_machine("server4090", "ssh", "fake-server", "/srv/research", gpu_count=1)
    return project, experiment, card


def test_single_gpu_lock_and_force_boundary(rf_env):
    add_machine("local4090", "local", None, str(rf_env["home"] / "compute"))
    lock = acquire_gpu_lock("local4090", "EXP-0001", "JOB-1", "tester")
    assert lock_status("local4090")["locked"] is True
    with pytest.raises(ResearchFlowError, match="already locked"):
        acquire_gpu_lock("local4090", "EXP-0002", "JOB-2", "tester")
    with pytest.raises(ResearchFlowError, match="Refusing to unlock"):
        release_gpu_lock("local4090")
    with pytest.raises(ResearchFlowError, match="explicit --yes"):
        release_gpu_lock("local4090", force=True)
    release_gpu_lock("local4090", force=True, confirmed=True)
    assert lock_status("local4090")["locked"] is False
    assert [item["event"] for item in read_jsonl(jobs_path())][:4] == ["QUEUED", "PREFLIGHT", "GPU_WAIT", "RUNNING"]


def test_stale_lock_can_be_released_without_force(rf_env):
    add_machine("gpu", "local", None, str(rf_env["home"] / "compute"))
    write_yaml(lock_path("gpu"), {
        "machine": "gpu", "gpu": 0, "pid": 99999999, "host": __import__("socket").gethostname(),
        "job_id": "old", "owner": "tester", "experiment": "EXP-0001",
        "started_at": (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(),
    })
    assert lock_status("gpu")["stale"] is True
    release_gpu_lock("gpu")
    assert not lock_path("gpu").exists()


def test_remote_plan_uses_persistent_paths_and_small_sync_only(rf_env):
    add_machine("server4090", "ssh", "server4090", "/srv/research")
    plan = remote_plan("server4090", "embodied-nav", "EXP-0023", "abc123", "python train.py --pilot")
    assert plan["remote_repo"] == "/srv/research/repos/embodied-nav"
    assert plan["remote_worktree"] == "/srv/research/worktrees/EXP-0023"
    assert "datasets" in plan["never_auto_sync"]
    assert plan["ssh_command"][0:2] == ["ssh", "server4090"]


def test_remote_submit_dry_run_is_side_effect_free(rf_env):
    project, experiment, _ = _remote_test_experiment(rf_env)
    result = remote_submit("server4090", "toy", experiment, "smoke", dry_run=True)
    assert result["run_id"] == "RUN-DRYRUN"
    assert result["gpu_count"] == 0
    assert result["test_only"] is True
    assert result["remote_repo"] == "/srv/research/repos/toy"
    assert not read_jsonl(project.root / "runs" / "registry.jsonl")


def test_remote_collect_registers_small_test_artifacts(rf_env, monkeypatch):
    project, experiment, card = _remote_test_experiment(rf_env)
    project.experiments.transition(experiment, "SMOKE_TEST")
    run_id = "RUN-000001"
    job = {
        "run_id": run_id,
        "project": "toy",
        "experiment": experiment,
        "level": "smoke",
        "state": "SUCCEEDED",
        "command": card["run"]["command"],
        "commit": card["experiment_commit"],
        "gpu_count": 0,
        "test_only": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "exit_code": 0,
        "error": None,
        "remote_repo": "/srv/research/repos/toy",
        "remote_worktree": f"/srv/research/worktrees/toy/{run_id}",
        "remote_run_root": f"/srv/research/runs/{run_id}",
        "remote_lock": "/srv/research/locks/gpu0.lock",
    }
    artifacts = {
        "job.json": json.dumps(job).encode(),
        "events.jsonl": b'{"event":"PREFLIGHT"}\n{"event":"RUNNING"}\n{"event":"SUCCEEDED"}\n',
        "run.log": b"# TEST / MOCK\n",
        "environment.json": json.dumps({"python": "3.10", "platform": "fake", "host": "fake-server", "gpu": []}).encode(),
        "metrics.json": json.dumps({"score": 6, "fixture": "TEST / MOCK"}).encode(),
        "experiment-card.yaml": b"id: TEST\n",
        "supervisor.log": b"",
    }
    monkeypatch.setattr(
        "researchflow.compute.remote_job_status",
        lambda machine, rid: {"machine": machine, **job},
    )

    def fake_read(machine, path, *, required=True, max_bytes=10 * 1024 * 1024):
        value = artifacts.get(Path(path).name)
        if value is None and required:
            raise AssertionError(path)
        return value

    monkeypatch.setattr("researchflow.compute._read_remote_small", fake_read)
    record = remote_collect("server4090", "toy", run_id)
    assert record["status"] == "succeeded"
    assert record["metrics"]["score"] == 6
    assert record["test_only"] is True
    assert (project.root / "runs" / run_id / "run.yaml").is_file()
    assert (project.root / "runs" / run_id / "events.jsonl").read_text(encoding="utf-8").count("\n") == 3
    assert record["artifacts"]["job_events"].endswith("events.jsonl")
    assert project.experiments.get(experiment)["status"] == "PILOT"
    events = read_jsonl(project.root / "runs" / "registry.jsonl")
    assert events[-1]["event"] == "registered"
