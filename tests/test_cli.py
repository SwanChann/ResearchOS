from researchflow.cli import _configure_utf8_output, main, parser
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


def test_windows_redirected_output_is_reconfigured_to_utf8():
    class FakeStream:
        def __init__(self, encoding="gbk", isatty=False):
            self.encoding = encoding
            self._isatty = isatty
            self.reconfigured = []

        def isatty(self):
            return self._isatty

        def reconfigure(self, **kwargs):
            self.reconfigured.append(kwargs)

    redirected = FakeStream()
    terminal = FakeStream(isatty=True)
    already_utf8 = FakeStream(encoding="utf-8")

    _configure_utf8_output((redirected, terminal, already_utf8), platform="win32")

    assert redirected.reconfigured == [{"encoding": "utf-8"}]
    assert terminal.reconfigured == []
    assert already_utf8.reconfigured == []


def test_doctor_detects_manually_broken_reference(rf_env, capsys):
    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    project = ResearchProject.open("toy")
    observation = add_observation(project, "Fixture", "TEST")
    decision = add_decision(project, "Bounded test", "Fixture only", [observation])
    path = project.root / "memory" / "decisions" / f"{decision}.md"
    path.write_text(path.read_text(encoding="utf-8").replace(observation, "OBS-9999"), encoding="utf-8")
    assert main(["doctor"]) == 1
    assert "OBS-9999" in capsys.readouterr().out


def test_compute_does_not_require_a_project_and_plan_command_is_not_shadowed(rf_env, capsys):
    assert main([
        "compute", "add", "server4090", "--type", "ssh", "--host", "research4090",
        "--workspace-root", "/home/yifei/researchflow", "--gpu-count", "1",
    ]) == 0
    assert main([
        "compute", "plan", "server4090", "--project-id", "embodied-nav",
        "--experiment", "EXP-0023", "--commit", "abc123", "--command", "python train.py --pilot",
    ]) == 0
    output = capsys.readouterr().out
    assert "ssh_command" in output
    assert "python train.py --pilot" in output


def test_unreachable_compute_probe_returns_failure(rf_env, monkeypatch, capsys):
    assert main([
        "compute", "add", "offline", "--type", "ssh", "--host", "offline",
        "--workspace-root", "/tmp/researchflow",
    ]) == 0
    monkeypatch.setattr("researchflow.compute.probe_machine", lambda name, dry_run=False: {
        "machine": name, "reachable": False, "stderr": "test unreachable", "probed": True,
    })
    assert main(["compute", "probe", "offline"]) == 1
    assert "reachable: false" in capsys.readouterr().out


def test_leaf_command_option_does_not_replace_top_level_route():
    args = parser().parse_args([
        "experiment", "new", "--hypothesis", "HYP-0001", "--title", "TEST",
        "--question", "TEST?", "--command", "python baseline.py", "--allowed-paths", "baseline.py",
        "--primary", "score", "--secondary", "exit_code", "--guardrails", '{"runtime": 1}',
        "--stop-conditions", "max_runs",
    ])
    assert args.root_command == "experiment"
    assert args.command == "python baseline.py"
