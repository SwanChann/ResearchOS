from datetime import datetime, timedelta, timezone

import pytest

from researchflow.compute import (
    acquire_gpu_lock,
    add_machine,
    jobs_path,
    lock_path,
    lock_status,
    release_gpu_lock,
    remote_plan,
)
from researchflow.errors import ResearchFlowError
from researchflow.io import read_jsonl, write_yaml


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
