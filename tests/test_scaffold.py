from pathlib import Path

import pytest

from researchflow.errors import ResearchFlowError, ValidationError
from researchflow.io import markdown_record, read_markdown_record, read_yaml, write_yaml
from researchflow.literature import LiteratureMatrixStore
from researchflow.project import ResearchProject, add_project
from researchflow.review import migrate_paper_verification
from researchflow.scaffold import (
    artifact_scaffold,
    matrix_entry_scaffold,
    paper_analysis_scaffold,
    preflight,
    synthesis_idea_scaffold,
)


def _verified_paper(project: ResearchProject, tmp_path: Path) -> str:
    pdf = tmp_path / "scaffold.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% TEST\n")
    paper_id = project.evidence.add_paper(pdf, "Scaffold TEST", authors=["Fixture"], year=2026)
    path = project.root / "evidence" / "papers" / "analysis" / f"{paper_id}.md"
    metadata, body = read_markdown_record(path)
    body = body.replace("Needs verification.", "TEST content.").replace("| C01 | TEST content. | - | - | - | - |", "| C01 | TEST claim | S1 | p. 2 | TEST | TEST |")
    path.write_text(markdown_record(metadata, body), encoding="utf-8")
    project.evidence.verify_paper(
        paper_id, sha256="A" * 64, source_version="TEST-v1", page_count=2,
        core_operator="TEST", primary_logic="TEST", methods=["TEST"],
    )
    return paper_id


def test_scaffolds_are_atomic_and_preflighted(rf_env, tmp_path):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    paper_id = _verified_paper(project, tmp_path)
    matrix = LiteratureMatrixStore(project)
    matrix.initialize("TEST", "TEST")

    paper_draft = tmp_path / "paper draft.md"
    paper_analysis_scaffold(project, paper_id, paper_draft)
    with pytest.raises(ResearchFlowError, match="placeholder"):
        preflight(project, "paper-analysis", paper_draft)
    with pytest.raises(ResearchFlowError, match="already exists"):
        paper_analysis_scaffold(project, paper_id, paper_draft)

    entry = tmp_path / "matrix entry.yaml"
    matrix_entry_scaffold(project, paper_id, entry)
    assert preflight(project, "matrix-entry", entry)["valid"] is True

    synthesis = tmp_path / "synthesis.yaml"
    synthesis_idea_scaffold(project, synthesis)
    with pytest.raises(ValidationError):
        preflight(project, "matrix-synthesis", synthesis)

    artifact_path = project.root / ".research" / "trace.json"
    artifact_path.write_text("{}\n", encoding="utf-8")
    request = tmp_path / "artifact.yaml"
    artifact_scaffold(request, artifact_path, "TEST trace", "trace-manifest")
    assert read_yaml(request)["agent_generated_draft"] is True
    assert preflight(project, "artifact", request)["valid"] is True


def test_paper_verification_migration_is_dry_run_backed_up_and_idempotent(rf_env, tmp_path):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    paper_id = _verified_paper(project, tmp_path)
    path = project.root / "evidence" / "papers" / "analysis" / f"{paper_id}.md"
    metadata, body = read_markdown_record(path)
    metadata.pop("verification")
    path.write_text(markdown_record(metadata, body), encoding="utf-8")

    before = path.read_bytes()
    preview = migrate_paper_verification(project, dry_run=True)
    assert preview["count"] == 1 and path.read_bytes() == before
    result = migrate_paper_verification(project)
    assert Path(result["backup_snapshot"]).exists()
    assert "verification" in read_markdown_record(path)[0]
    replay = migrate_paper_verification(project)
    assert replay["count"] == 0 and replay["changed"] is False


def test_scaffold_and_preflight_cli_smoke(rf_env, tmp_path, capsys):
    from researchflow.cli import main

    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    project = ResearchProject.open("toy")
    paper_id = _verified_paper(project, tmp_path)
    LiteratureMatrixStore(project).initialize("TEST", "TEST")
    output = tmp_path / "entry.yaml"
    assert main(["scaffold", "matrix-entry", paper_id, "--output", str(output)]) == 0
    assert main(["preflight", "matrix-entry", str(output)]) == 0
    assert "semantic correctness is not" in capsys.readouterr().out
