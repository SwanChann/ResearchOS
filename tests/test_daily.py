from datetime import datetime

from researchflow.daily import create_daily_log
from researchflow.io import append_jsonl
from researchflow.project import ResearchProject, add_project, update_current_state
from researchflow.records import add_observation


def test_daily_log_only_summarizes_decision_relevant_records(rf_env):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    observation = add_observation(project, "TEST", "TEST fixture output")
    path = create_daily_log(project)
    text = open(path, encoding="utf-8").read()
    assert observation in text
    assert "New runs: none." in text
    assert "New runs: registry" not in text
    assert "运行了 ls" not in text


def test_daily_log_reads_registered_runs_and_current_state(rf_env):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    append_jsonl(
        project.root / "runs" / "registry.jsonl",
        {
            "event": "registered",
            "id": "RUN-000001",
            "at": datetime.now().astimezone().isoformat(),
        },
    )
    update_current_state(project, "Open Blockers", "- Dataset receipt is missing.")
    update_current_state(project, "Next Action", "Review the dataset receipt.")

    text = open(create_daily_log(project), encoding="utf-8").read()
    assert "New runs: RUN-000001." in text
    assert "- Dataset receipt is missing." in text
    assert "- Review the dataset receipt." in text
