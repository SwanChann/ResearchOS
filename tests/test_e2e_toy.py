import json
import shutil
import subprocess
from pathlib import Path

from researchflow.experiments import worktree_path
from researchflow.gitops import create_worktree, head
from researchflow.project import ResearchProject, add_project
from researchflow.records import add_decision, add_hypothesis, add_observation, broken_references
from researchflow.runs import execute_local_run


def commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", message], check=True, capture_output=True)


def test_complete_toy_research_loop_is_reproducible(rf_env):
    fixture = Path(__file__).parents[1] / "examples" / "toy-research" / "baseline.py"
    shutil.copy2(fixture, rf_env["repo"] / "baseline.py")
    subprocess.run(["git", "init", "-b", "main", str(rf_env["repo"])], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(rf_env["repo"]), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(rf_env["repo"]), "config", "user.email", "test@example.invalid"], check=True)
    commit(rf_env["repo"], "TEST baseline")

    add_project("toy", rf_env["repo"], "Toy Research (TEST)")
    project = ResearchProject.open("toy")
    repository = project.evidence.add_repo(
        "TEST fixture repository",
        head(project.repo),
        local=project.repo,
        tags=["TEST", "MOCK"],
        notes="Deterministic fixture only; not scientific evidence.",
    )
    initial = add_observation(
        project,
        "TEST baseline output",
        "The deterministic fixture uses MULTIPLIER=1.",
        [repository],
        observation_type="project_observation",
    )
    hypothesis = add_hypothesis(project, "TEST multiplier", "Setting MULTIPLIER=2 doubles the fixture score.", [initial], falsification="Input 3 does not produce score 6.")
    experiment = project.experiments.create(
        hypothesis, "TEST deterministic multiplier", "Does the fixture score double?",
        "python baseline.py --input 3", ["baseline.py"], [], "score", ["exit_code"],
        {"runtime_seconds_max": 10}, ["nonzero_exit", "max_runs"], test_only=True,
    )
    card = project.experiments.get(experiment)
    target = worktree_path(project, experiment)
    create_worktree(project.repo, target, card["baseline"]["commit"])
    source = (target / "baseline.py").read_text(encoding="utf-8").replace("MULTIPLIER = 1", "MULTIPLIER = 2")
    (target / "baseline.py").write_text(source, encoding="utf-8")
    subprocess.run(["git", "-C", str(target), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(target), "config", "user.email", "test@example.invalid"], check=True)
    commit(target, "TEST experiment change")
    for state in ("EVIDENCE_READY", "HYPOTHESIS_APPROVED", "IMPLEMENTED", "SMOKE_TEST"):
        project.experiments.transition(experiment, state)

    smoke = execute_local_run(project, experiment, "smoke")
    assert smoke["status"] == "succeeded"
    assert smoke["metrics"] == {"score": 6, "fixture": "TEST / MOCK"}
    project.experiments.transition(experiment, "PILOT")
    pilot = execute_local_run(project, experiment, "pilot")
    assert pilot["metrics"] == smoke["metrics"]
    project.experiments.transition(experiment, "PILOT_PASS")
    approved = project.experiments.get(experiment)
    approved["approval"]["full"] = "approved"
    from researchflow.io import write_yaml
    write_yaml(project.experiments.path(experiment), approved)
    project.experiments.transition(experiment, "FULL_APPROVED")
    project.experiments.transition(experiment, "FULL_RUN")
    full = execute_local_run(project, experiment, "full")
    assert full["metrics"] == smoke["metrics"]
    project.experiments.transition(experiment, "ANALYZED")
    result_observation = add_observation(project, "TEST repeatability", "Three fixture levels produced identical score 6.", [full["id"]], "high", "experimental_result")
    project.experiments.transition(experiment, "DECIDED")
    decision = add_decision(project, "Accept TEST fixture change", "Deterministic E2E contract passed; this is not scientific evidence.", [experiment, result_observation, full["id"]])
    project.experiments.transition(experiment, "ACCEPTED")

    run_record = project.root / "runs" / full["id"] / "run.yaml"
    assert run_record.is_file()
    assert json.loads((run_record.parent / "metrics.json").read_text(encoding="utf-8"))["score"] == 6
    assert (run_record.parent / "run.log").is_file()
    assert (run_record.parent / "environment.json").is_file()
    assert full["git"]["commit"] == project.experiments.get(experiment)["experiment_commit"]
    assert full["test_only"] is True
    assert (project.root / "memory" / "decisions" / f"{decision}.md").is_file()
    status = project.status()
    assert status["latest_experiment"]["status"] == "ACCEPTED"
    assert status["latest_decision"] == decision

    reopened = ResearchProject.open("toy")
    recovered_status = reopened.status()
    assert recovered_status["latest_experiment"]["status"] == "ACCEPTED"
    assert recovered_status["latest_decision"] == decision
    assert recovered_status["last_result"]["id"] == full["id"]
    assert broken_references(reopened) == []
    assert (reopened.root / "AGENTS.md").read_text(encoding="utf-8").startswith("# Project Agent Protocol")
    assert "memory/current-state.md" in (reopened.root / "KNOWLEDGE.md").read_text(encoding="utf-8")
