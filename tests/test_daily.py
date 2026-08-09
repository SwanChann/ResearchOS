from researchflow.daily import create_daily_log
from researchflow.project import ResearchProject, add_project
from researchflow.records import add_observation


def test_daily_log_only_summarizes_decision_relevant_records(rf_env):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    observation = add_observation(project, "TEST", "TEST fixture output")
    path = create_daily_log(project)
    text = open(path, encoding="utf-8").read()
    assert observation in text
    assert "运行了 ls" not in text
