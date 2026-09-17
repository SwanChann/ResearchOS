import pytest

from researchflow.artifact import ArtifactStore
from researchflow.errors import ResearchFlowError
from researchflow.knowledge import BEGIN, END, KnowledgeStore
from researchflow.project import ResearchProject, add_project
from researchflow.records import add_observation


def _project(rf_env) -> ResearchProject:
    add_project("toy", rf_env["repo"])
    return ResearchProject.open("toy")


def test_knowledge_rebuild_is_idempotent_and_preserves_manual_regions(rf_env):
    project = _project(rf_env)
    knowledge_path = project.root / "KNOWLEDGE.md"
    manual = "\n## Human Notes\n\n保留这段人工说明。\n"
    knowledge_path.write_text(knowledge_path.read_text(encoding="utf-8") + manual, encoding="utf-8")
    observation_id = add_observation(project, "TEST observation", "TEST fixture only")
    artifact_path = project.root / ".research" / "audit.md"
    artifact_path.write_text("TEST artifact\n", encoding="utf-8")
    artifact_id = ArtifactStore(project).add(artifact_path, title="TEST audit", artifact_type="audit")["artifact"]["id"]

    knowledge = KnowledgeStore(project)
    before_preview = knowledge_path.read_text(encoding="utf-8")
    preview = knowledge.rebuild(dry_run=True)
    assert preview["changed"] is True
    assert knowledge_path.read_text(encoding="utf-8") == before_preview
    assert knowledge.rebuild()["changed"] is True
    first = knowledge_path.read_text(encoding="utf-8")
    assert "保留这段人工说明" in first
    assert observation_id in first and artifact_id in first
    assert first.count(BEGIN) == 1 and first.count(END) == 1
    assert knowledge.rebuild()["changed"] is False
    assert knowledge_path.read_text(encoding="utf-8") == first
    assert knowledge.check()["valid"] is True


def test_knowledge_detects_stale_registry_and_broken_navigation(rf_env):
    project = _project(rf_env)
    knowledge = KnowledgeStore(project)
    knowledge.rebuild()
    new_path = project.root / ".research" / "new.md"
    new_path.write_text("TEST\n", encoding="utf-8")
    artifact_id = ArtifactStore(project).add(new_path, title="New", artifact_type="report")["artifact"]["id"]
    stale = knowledge.check()
    assert stale["stale"] is True
    assert artifact_id in stale["missing_registered_ids"]

    knowledge.rebuild()
    text = knowledge.path.read_text(encoding="utf-8").replace(".research/new.md", ".research/missing.md")
    knowledge.path.write_text(text, encoding="utf-8")
    assert knowledge.check()["broken_links"] == [".research/missing.md"]


def test_knowledge_rejects_ambiguous_generated_markers(rf_env):
    project = _project(rf_env)
    knowledge = KnowledgeStore(project)
    knowledge.rebuild()
    current = knowledge.path.read_text(encoding="utf-8")
    knowledge.path.write_text(current + f"\n{BEGIN}\nextra\n{END}\n", encoding="utf-8")
    with pytest.raises(ResearchFlowError, match="ambiguous generated-region markers"):
        knowledge.check()
    with pytest.raises(ResearchFlowError, match="ambiguous generated-region markers"):
        knowledge.rebuild()


def test_status_uses_registry_and_verbose_exposes_entries(rf_env, monkeypatch):
    project = _project(rf_env)
    add_observation(project, "TEST observation", "TEST fixture only")
    original = KnowledgeStore.inventory
    calls = 0

    def counted(self):
        nonlocal calls
        calls += 1
        return original(self)

    monkeypatch.setattr(KnowledgeStore, "inventory", counted)
    concise = project.status()
    assert calls == 1
    assert concise["registry_summary"]["records"] == 1
    assert "registry_entries" not in concise
    calls = 0
    verbose = project.status(verbose=True)
    assert calls == 1
    assert verbose["registry_entries"][0]["kind"] == "Observation"
    assert verbose["artifact_verification"]["valid"] is True


def test_knowledge_cli_rebuild_and_check(rf_env, capsys):
    from researchflow.cli import main

    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    assert main(["knowledge", "rebuild", "--dry-run"]) == 0
    assert "dry_run: true" in capsys.readouterr().out
    assert main(["knowledge", "rebuild"]) == 0
    assert main(["knowledge", "check"]) == 0
