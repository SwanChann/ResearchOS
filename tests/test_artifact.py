from pathlib import Path

import pytest

from researchflow.artifact import ArtifactStore
from researchflow.errors import ResearchFlowError
from researchflow.io import read_yaml, write_yaml
from researchflow.project import ResearchProject, add_project


def _project(rf_env) -> ResearchProject:
    add_project("toy", rf_env["repo"])
    return ResearchProject.open("toy")


def test_artifact_add_list_show_verify_refresh_and_idempotency(rf_env):
    project = _project(rf_env)
    report = project.root / ".research" / "审核报告.md"
    report.write_text("TEST v1\n", encoding="utf-8")
    store = ArtifactStore(project)
    result = store.add(report, title="TEST audit", artifact_type="audit-report", status="active")
    artifact_id = result["artifact"]["id"]
    assert result["created"] is True
    assert store.add(report, title="TEST audit", artifact_type="audit-report", status="active")["idempotent"] is True
    assert store.list()[0]["id"] == artifact_id
    assert store.show(artifact_id)["path"] == ".research/审核报告.md"
    verification = store.verify(artifact_id)
    assert verification["valid"] is True
    assert "scientific claims are not established" in verification["meaning"]

    report.write_text("TEST v2\n", encoding="utf-8")
    assert store.verify(artifact_id)["valid"] is False
    refreshed = store.refresh(artifact_id)
    assert refreshed["sha256"] != result["artifact"]["sha256"]
    assert store.verify(artifact_id)["valid"] is True


def test_artifact_rejects_escape_broken_reference_and_path_conflict(rf_env, tmp_path):
    project = _project(rf_env)
    outside = tmp_path / "outside.md"
    outside.write_text("TEST\n", encoding="utf-8")
    store = ArtifactStore(project)
    with pytest.raises(ResearchFlowError, match="escapes"):
        store.add(outside, title="TEST", artifact_type="audit")

    inside = project.root / ".research" / "inside.md"
    inside.write_text("TEST\n", encoding="utf-8")
    with pytest.raises(ResearchFlowError, match="Broken artifact reference"):
        store.add(inside, title="TEST", artifact_type="audit", derived_from=["PAPER-9999"])
    store.add(inside, title="TEST", artifact_type="audit")
    with pytest.raises(ResearchFlowError, match="different metadata"):
        store.add(inside, title="Changed title", artifact_type="audit")


def test_artifact_superseded_chain_is_preserved(rf_env):
    project = _project(rf_env)
    old_path = project.root / ".research" / "old.md"
    new_path = project.root / ".research" / "new.md"
    old_path.write_text("OLD TEST\n", encoding="utf-8")
    new_path.write_text("NEW TEST\n", encoding="utf-8")
    store = ArtifactStore(project)
    old_id = store.add(old_path, title="Old", artifact_type="report")["artifact"]["id"]
    new_id = store.add(new_path, title="New", artifact_type="report")["artifact"]["id"]
    assert store.supersede(old_id, new_id)["changed"] is True
    assert store.supersede(old_id, new_id)["changed"] is False
    assert store.show(old_id)["status"] == "superseded"
    assert store.show(old_id)["superseded_by"] == new_id
    assert store.show(new_id)["supersedes"] == [old_id]
    assert old_path.exists()
    with pytest.raises(ResearchFlowError, match="cycle"):
        store.supersede(new_id, old_id)


def test_artifact_registry_rejects_manual_path_escape(rf_env, tmp_path):
    project = _project(rf_env)
    report = project.root / ".research" / "inside.md"
    report.write_text("TEST\n", encoding="utf-8")
    store = ArtifactStore(project)
    store.add(report, title="TEST", artifact_type="report")
    registry = read_yaml(store.path)
    registry["artifacts"][0]["path"] = "../../outside.md"
    write_yaml(store.path, registry)
    with pytest.raises(ResearchFlowError, match="unsafe project-relative path"):
        store.load()
    assert not (tmp_path / "outside.md").exists()


def test_artifact_migration_dry_run_and_actual_backup(rf_env):
    project = _project(rf_env)
    legacy = project.root / ".research" / "legacy"
    legacy.mkdir()
    (legacy / "历史.md").write_text("TEST\n", encoding="utf-8")
    store = ArtifactStore(project)
    preview = store.migrate(legacy, dry_run=True)
    assert preview["count"] == 1
    assert store.list() == []
    result = store.migrate(legacy)
    assert result["count"] == 1
    assert Path(result["backup_snapshot"]).exists()
    assert store.list()[0]["status"] == "draft"
    assert store.migrate(legacy, dry_run=True)["count"] == 0


def test_artifact_cli_smoke(rf_env, capsys):
    from researchflow.cli import main

    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    project = ResearchProject.open("toy")
    path = project.root / ".research" / "trace.json"
    path.write_text("{}\n", encoding="utf-8")
    assert main(["artifact", "add", str(path), "--title", "Trace", "--type", "trace-manifest"]) == 0
    output = capsys.readouterr().out
    assert "ARTIFACT-0001" in output
    assert main(["artifact", "verify", "ARTIFACT-0001"]) == 0
