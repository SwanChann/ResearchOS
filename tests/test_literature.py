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
    assert main(["evidence", "matrix", "render"]) == 0
