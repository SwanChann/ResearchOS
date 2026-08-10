from pathlib import Path

import pytest

from researchflow.errors import ResearchFlowError
from researchflow.io import markdown_record, read_markdown_record, write_yaml
from researchflow.literature import DEFAULT_AXES, LiteratureMatrixStore
from researchflow.project import ResearchProject, add_project


def verified_paper(project: ResearchProject, tmp_path: Path, title: str = "TEST Paper") -> str:
    pdf = tmp_path / f"{title}.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% TEST FIXTURE\n")
    paper_id = project.evidence.add_paper(pdf, title, authors=["Test Author"], year=2026)
    path = project.root / "evidence" / "papers" / "analysis" / f"{paper_id}.md"
    metadata, _ = read_markdown_record(path)
    body = f"""# {title}

## Source Snapshot
TEST source.

## Claim Strength Scale
S1 direct result.

## Verified Claims
| ID | Claim | Strength | PDF page(s) |
|---|---|---|---|
| C01 | TEST claim | S1 | p. 2 |

## Critical Assessment
TEST only.

## Idea Seeds
### IDEA-01 - TEST seed
Smallest falsification test: TEST.
"""
    path.write_text(markdown_record(metadata, body), encoding="utf-8")
    project.evidence.verify_paper(
        paper_id,
        sha256="A" * 64,
        source_version="TEST-v1",
        page_count=2,
        core_operator="TEST operator",
        primary_logic="TEST logic",
        methods=["TEST method"],
    )
    return paper_id


def complete_entry(paper_id: str) -> dict:
    return {
        "paper_id": paper_id,
        "role": "TEST central evidence",
        "decision": "central",
        "next_checks": ["TEST artifact audit"],
        "cells": {
            axis["id"]: {
                "status": "supported",
                "text": f"TEST {axis['id']}",
                "evidence": [{"pages": "p. 2", "claim_ids": ["C01"], "locator": "TEST table"}],
            }
            for axis in DEFAULT_AXES
        },
    }


def test_matrix_rejects_missing_axis_and_appends_verified_paper(rf_env, tmp_path):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    paper_id = verified_paper(project, tmp_path)
    matrix = LiteratureMatrixStore(project)
    matrix.initialize("TEST matrix", "TEST verified papers")

    incomplete = complete_entry(paper_id)
    incomplete["cells"].pop("failure_boundary")
    with pytest.raises(ResearchFlowError, match="missing axes: failure_boundary"):
        matrix.add_entry(incomplete)

    assert matrix.add_entry(complete_entry(paper_id)) == paper_id
    summary = matrix.validate()
    assert summary["papers"] == 1
    assert summary["axes"] == len(DEFAULT_AXES)
    assert summary["cell_status"]["supported"] == len(DEFAULT_AXES)
    _, body = read_markdown_record(matrix.path)
    assert "PAPER-0001 C01 p. 2 TEST table" in body
    assert "../evidence/papers/analysis/PAPER-0001.md" in body

    with pytest.raises(ResearchFlowError, match="already contains"):
        matrix.add_entry(complete_entry(paper_id))


def test_matrix_rejects_broken_claim_and_stale_source(rf_env, tmp_path):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    paper_id = verified_paper(project, tmp_path)
    matrix = LiteratureMatrixStore(project)
    matrix.initialize("TEST matrix", "TEST verified papers")

    broken = complete_entry(paper_id)
    broken["cells"]["main_results"]["evidence"][0]["claim_ids"] = ["C99"]
    with pytest.raises(ResearchFlowError, match="C99 is absent"):
        matrix.add_entry(broken)

    matrix.add_entry(complete_entry(paper_id))
    record, body = read_markdown_record(matrix.path)
    record["papers"][0]["source_version"] = "TEST-v2"
    matrix.path.write_text(markdown_record(record, body), encoding="utf-8")
    with pytest.raises(ResearchFlowError, match="entry is stale"):
        matrix.validate()


def test_matrix_cli_init_add_validate_and_render(rf_env, tmp_path, capsys):
    from researchflow.cli import main

    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    project = ResearchProject.open("toy")
    paper_id = verified_paper(project, tmp_path)
    assert main(["evidence", "matrix", "init", "--title", "TEST matrix", "--scope", "TEST scope"]) == 0

    entry_path = tmp_path / "entry.yaml"
    write_yaml(entry_path, complete_entry(paper_id))
    assert main(["evidence", "matrix", "add", str(entry_path)]) == 0
    assert main(["evidence", "matrix", "validate"]) == 0
    assert "valid: true" in capsys.readouterr().out
    synthesis_path = tmp_path / "synthesis.yaml"
    write_yaml(synthesis_path, synthesis_update(paper_id))
    assert main(["evidence", "matrix", "synthesize", str(synthesis_path)]) == 0
    assert "changed: true" in capsys.readouterr().out
    assert main(["evidence", "matrix", "synthesize", str(synthesis_path)]) == 0
    assert "changed: false" in capsys.readouterr().out
    assert main(["evidence", "matrix", "render"]) == 0


def synthesis_update(*paper_ids: str, mode: str = "replace") -> dict:
    evidence = [
        {"paper_id": paper_id, "pages": "p. 2", "claim_ids": ["C01"], "locator": "TEST table"}
        for paper_id in paper_ids
    ]
    return {
        "matrix_id": "LITMATRIX-0001",
        "mode": mode,
        "syntheses": [{
            "id": "SYN-001",
            "statement": "TEST synthesis",
            "strength": "paper_consensus",
            "evidence": evidence,
            "caveat": "TEST caveat",
        }],
        "ideas": [{
            "id": "XIDEA-001",
            "title": "TEST idea",
            "trigger": "TEST trigger",
            "mechanism": "TEST mechanism",
            "falsification": "TEST falsification",
            "risks": "TEST risks",
            "novelty": "unchecked",
            "evidence": evidence,
        }],
    }


def test_matrix_synthesis_replace_is_validated_atomic_and_idempotent(rf_env, tmp_path):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    first = verified_paper(project, tmp_path, "TEST Paper One")
    second = verified_paper(project, tmp_path, "TEST Paper Two")
    matrix = LiteratureMatrixStore(project)
    matrix.initialize("TEST matrix", "TEST verified papers")
    matrix.add_entry(complete_entry(first))
    matrix.add_entry(complete_entry(second))

    update = synthesis_update(first, second)
    result = matrix.synthesize(update)
    assert result["changed"] is True
    assert result["syntheses"] == 1
    assert result["ideas"] == 1
    before = matrix.path.read_text(encoding="utf-8")
    assert matrix.synthesize(update)["changed"] is False
    assert matrix.path.read_text(encoding="utf-8") == before
    assert matrix.validate()["syntheses"] == 1

    broken = synthesis_update(first, second)
    broken["syntheses"][0]["evidence"][0]["claim_ids"] = ["C99"]
    with pytest.raises(ResearchFlowError, match="C99 is absent"):
        matrix.synthesize(broken)
    assert matrix.path.read_text(encoding="utf-8") == before


def test_matrix_synthesis_upsert_preserves_unmentioned_records(rf_env, tmp_path):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    paper_id = verified_paper(project, tmp_path)
    matrix = LiteratureMatrixStore(project)
    matrix.initialize("TEST matrix", "TEST verified papers")
    matrix.add_entry(complete_entry(paper_id))
    matrix.synthesize(synthesis_update(paper_id))

    update = synthesis_update(paper_id, mode="upsert")
    update["syntheses"][0]["statement"] = "TEST updated synthesis"
    update["ideas"] = []
    assert matrix.synthesize(update)["changed"] is True
    record = matrix.load()
    assert record["syntheses"][0]["statement"] == "TEST updated synthesis"
    assert len(record["ideas"]) == 1

    duplicate = synthesis_update(paper_id, mode="upsert")
    duplicate["syntheses"].append({**duplicate["syntheses"][0], "statement": "TEST duplicate"})
    with pytest.raises(ResearchFlowError, match="duplicate syntheses IDs"):
        matrix.synthesize(duplicate)
