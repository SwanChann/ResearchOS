import os
import argparse
import subprocess
import sys

import pytest

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


def test_project_show_exposes_cross_session_startup_paths(rf_env, capsys):
    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    assert main(["project", "show", "toy"]) == 0
    output = capsys.readouterr().out
    assert f"workspace: {rf_env['home'] / '.projects' / 'toy'}" in output
    assert "AGENTS.md" in output
    assert "KNOWLEDGE.md" in output
    assert "memory\\current-state.md" in output or "memory/current-state.md" in output
    assert "rf --project toy status" in output


def test_cli_status_works_from_unrelated_working_directory(rf_env, tmp_path):
    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    unrelated = tmp_path / "unrelated-folder"
    unrelated.mkdir()
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "researchflow.cli", "--project", "toy", "status"],
        cwd=unrelated,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "id: toy" in result.stdout
    assert str(rf_env["repo"]) in result.stdout


def test_doctor_skips_live_machine_probe_without_explicit_flag(rf_env, monkeypatch, capsys):
    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    assert main([
        "compute", "add", "offline", "--type", "ssh", "--host", "offline",
        "--workspace-root", "/tmp/researchflow",
    ]) == 0

    def unexpected_probe(name):
        raise AssertionError(f"unexpected live probe: {name}")

    monkeypatch.setattr("researchflow.doctor.probe_machine", unexpected_probe)
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "machine offline live probe" in output
    assert "skipped" in output


def test_doctor_live_probe_requires_explicit_flag(rf_env, monkeypatch, capsys):
    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    assert main([
        "compute", "add", "fixture", "--type", "ssh", "--host", "fixture",
        "--workspace-root", "/tmp/researchflow",
    ]) == 0
    called = []

    def fixture_probe(name):
        called.append(name)
        return {"machine": name, "reachable": True, "gpu": "TEST / MOCK GPU"}

    monkeypatch.setattr("researchflow.doctor.probe_machine", fixture_probe)
    assert main(["doctor", "--probe-machines"]) == 0
    assert called == ["fixture"]
    assert "TEST / MOCK GPU" in capsys.readouterr().out


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


def test_paper_verify_cli_arguments_do_not_shadow_top_level_route():
    args = parser().parse_args([
        "evidence", "paper", "verify", "PAPER-0001",
        "--sha256", "A" * 64,
        "--source-version", "TEST-v1",
        "--pages", "2",
        "--core-operator", "TEST operator",
        "--primary-logic", "TEST logic",
        "--methods", "TEST method",
    ])
    assert args.root_command == "evidence"
    assert args.action == "verify"


def test_literature_matrix_cli_arguments_route_to_matrix():
    args = parser().parse_args(["evidence", "matrix", "add", "entry.yaml"])
    assert args.root_command == "evidence"
    assert args.evidence_kind == "matrix"
    assert args.action == "add"

    synthesis_args = parser().parse_args(["evidence", "matrix", "synthesize", "synthesis.yaml"])
    assert synthesis_args.root_command == "evidence"
    assert synthesis_args.evidence_kind == "matrix"
    assert synthesis_args.action == "synthesize"


def test_corpus_gap_graph_and_migration_cli_routes():
    corpus = parser().parse_args([
        "evidence", "corpus", "create", "--matrix", "LITMATRIX-0001",
        "--title", "TEST", "--scope-file", "scope.yaml", "--dry-run",
    ])
    assert (corpus.root_command, corpus.evidence_kind, corpus.action) == ("evidence", "corpus", "create")

    gap = parser().parse_args([
        "evidence", "gap", "detect", "--corpus", "CORPUS-0001",
        "--motifs", "motifs.yaml", "--test-only", "--dry-run",
    ])
    assert (gap.evidence_kind, gap.action, gap.test_only) == ("gap", "detect", True)

    review = parser().parse_args([
        "evidence", "graph", "review", "--claim", "CLAIM-0001", "--file", "review.yaml",
    ])
    assert (review.evidence_kind, review.action, str(review.file)) == ("graph", "review", "review.yaml")

    migration = parser().parse_args([
        "migrate", "corpus-gap-evidence-graph", "--dry-run", "--snapshot-dir", "snapshots",
    ])
    assert (migration.root_command, migration.migration_kind, migration.dry_run) == (
        "migrate", "corpus-gap-evidence-graph", True,
    )


def test_paper_adjacency_cli_routes():
    build = parser().parse_args(["evidence", "adjacency", "build", "--corpus", "CORPUS-0001", "--dry-run"])
    assert (build.evidence_kind, build.action, build.corpus, build.dry_run) == (
        "adjacency", "build", "CORPUS-0001", True,
    )
    neighbors = parser().parse_args(["evidence", "adjacency", "neighbors", "PAPER-0001", "--top-k", "5"])
    assert (neighbors.action, neighbors.paper_id, neighbors.top_k, neighbors.status) == (
        "neighbors", "PAPER-0001", 5, "accepted",
    )
    scaffold = parser().parse_args([
        "scaffold", "paper-adjacency", "--corpus", "CORPUS-0001",
        "--from", "PAPER-0001", "--to", "PAPER-0002", "--output", "adjacency.yaml",
    ])
    assert (scaffold.scaffold_kind, scaffold.source, scaffold.target) == (
        "paper-adjacency", "PAPER-0001", "PAPER-0002",
    )


def test_every_cli_parser_node_has_working_help(capsys):
    root = parser()
    routes = [[]]

    def visit(current, prefix):
        for action in current._actions:
            if not isinstance(action, argparse._SubParsersAction):
                continue
            for name, child in action.choices.items():
                route = [*prefix, name]
                routes.append(route)
                visit(child, route)

    visit(root, [])
    for route in routes:
        with pytest.raises(SystemExit) as stopped:
            root.parse_args([*route, "--help"])
        assert stopped.value.code == 0, route
    assert len(routes) >= 140
    capsys.readouterr()
