from researchflow.cli import main


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

