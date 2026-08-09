from researchflow.cli import main
from researchflow.project import ResearchProject
from researchflow.records import add_decision, add_observation


def test_cli_project_memory_and_doctor(rf_env, capsys):
    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    assert main(["status"]) == 0
    assert main(["memory", "observation", "add", "--title", "Fixture", "--text", "TEST observation"]) == 0
    output = capsys.readouterr().out
    assert "OBS-0001" in output
    assert main(["doctor"]) == 0


def test_cli_error_has_fix_context(rf_env, capsys):
    assert main(["status"]) == 2
    assert "Project is ambiguous" in capsys.readouterr().err


def test_doctor_detects_manually_broken_reference(rf_env, capsys):
    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    project = ResearchProject.open("toy")
    observation = add_observation(project, "Fixture", "TEST")
    decision = add_decision(project, "Bounded test", "Fixture only", [observation])
    path = project.root / "memory" / "decisions" / f"{decision}.md"
    path.write_text(path.read_text(encoding="utf-8").replace(observation, "OBS-9999"), encoding="utf-8")
    assert main(["doctor"]) == 1
    assert "OBS-9999" in capsys.readouterr().out
