import subprocess

import pytest

from researchflow.errors import ResearchFlowError
from researchflow.experiments import ExperimentStore, preflight, worktree_path
from researchflow.gitops import create_worktree
from researchflow.project import ResearchProject, add_project
from researchflow.records import add_hypothesis, add_observation


def init_git_repo(path):
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.invalid"], check=True)
    (path / "src").mkdir()
    (path / "evaluation").mkdir()
    (path / "src" / "model.py").write_text("VALUE = 1\n", encoding="utf-8")
    (path / "evaluation" / "metric.py").write_text("METRIC = 'fixed'\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "baseline"], check=True, capture_output=True)


def experiment(rf_env):
    init_git_repo(rf_env["repo"])
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    observation = add_observation(project, "TEST baseline", "The deterministic fixture returns 1.")
    hypothesis = add_hypothesis(project, "TEST scaling", "Changing VALUE changes output.", [observation], falsification="VALUE remains 1.")
    exp = project.experiments.create(
        hypothesis, "TEST change", "Does VALUE change?", "python src/model.py",
        ["src"], ["evaluation"], "value", ["exit_code"], {"runtime_seconds": 5},
        ["nonzero_exit", "max_runs"],
    )
    return project, exp


def test_state_machine_rejects_illegal_jump(rf_env):
    project, exp = experiment(rf_env)
    with pytest.raises(ResearchFlowError, match="cannot transition DRAFT -> FULL_RUN"):
        project.experiments.transition(exp, "FULL_RUN")
    assert project.experiments.transition(exp, "EVIDENCE_READY")["status"] == "EVIDENCE_READY"


def test_preflight_blocks_dirty_and_frozen_changes(rf_env):
    project, exp = experiment(rf_env)
    for state in ("EVIDENCE_READY", "HYPOTHESIS_APPROVED", "IMPLEMENTED"):
        project.experiments.transition(exp, state)
    clean = preflight(project, exp, "smoke")
    assert all(check.ok for check in clean)
    (project.repo / "evaluation" / "metric.py").write_text("METRIC = 'changed'\n", encoding="utf-8")
    blocked = preflight(project, exp, "smoke")
    failures = {check.name for check in blocked if not check.ok}
    assert {"clean worktree", "frozen paths", "allowed paths"} <= failures


def test_worktree_dry_run_has_no_side_effect(rf_env):
    project, exp = experiment(rf_env)
    card = project.experiments.get(exp)
    target = worktree_path(project, exp)
    result = create_worktree(project.repo, target, card["baseline"]["commit"], dry_run=True)
    assert result.startswith("DRY-RUN:")
    assert not target.exists()
