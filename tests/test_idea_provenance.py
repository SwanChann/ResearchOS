from pathlib import Path

import pytest

from researchflow.errors import ResearchFlowError
from researchflow.io import markdown_record, read_markdown_record
from researchflow.literature import GENERIC_AXES, LiteratureMatrixStore
from researchflow.project import ResearchProject, add_project
from researchflow.records import add_hypothesis, hypothesis_provenance_status, show_record


def _project_with_idea(rf_env, tmp_path: Path) -> tuple[ResearchProject, str]:
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    pdf = tmp_path / "idea.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% TEST\n")
    paper_id = project.evidence.add_paper(pdf, "Idea TEST", authors=["Fixture"], year=2026)
    path = project.root / "evidence" / "papers" / "analysis" / f"{paper_id}.md"
    metadata, _ = read_markdown_record(path)
    body = """# TEST

## Source Snapshot
TEST.

## Claim Strength Scale
S1 direct.

## Verified Claims
| ID | Claim | PDF page(s) |
|---|---|---|
| C01 | TEST | p. 2 |

## Critical Assessment
TEST.

## Idea Seeds
### IDEA-01 - TEST
Smallest falsification test: TEST.
"""
    path.write_text(markdown_record(metadata, body), encoding="utf-8")
    project.evidence.verify_paper(
        paper_id, sha256="A" * 64, source_version="TEST-v1", page_count=2,
        core_operator="TEST", primary_logic="TEST", methods=["TEST"],
    )
    matrix = LiteratureMatrixStore(project)
    matrix.initialize("TEST", "TEST")
    matrix.add_entry({
        "paper_id": paper_id, "role": "TEST", "decision": "central", "next_checks": [],
        "cells": {
            axis["id"]: {
                "status": "supported", "text": "TEST",
                "evidence": [{"pages": "p. 2", "claim_ids": ["C01"], "locator": "TEST"}],
            } for axis in GENERIC_AXES
        },
    })
    matrix.synthesize({
        "matrix_id": "LITMATRIX-0001", "mode": "replace", "syntheses": [],
        "ideas": [{
            "id": "XIDEA-0001", "title": "TEST idea", "trigger": "TEST trigger",
            "mechanism": "TEST mechanism", "falsification": "TEST falsification", "risks": "TEST risk",
            "novelty": "unchecked",
            "evidence": [{"paper_id": paper_id, "pages": "p. 2", "claim_ids": ["C01"], "locator": "TEST"}],
        }],
    })
    return project, paper_id


def test_xidea_is_first_class_hypothesis_source_with_recursive_evidence(rf_env, tmp_path):
    project, paper_id = _project_with_idea(rf_env, tmp_path)
    hypothesis_id = add_hypothesis(
        project, "TEST hypothesis", "TEST statement", falsification="TEST falsification",
        ideas=["XIDEA-0001"],
    )
    metadata, body = show_record(project, hypothesis_id)
    assert metadata["based_on"]["ideas"] == ["XIDEA-0001"]
    assert metadata["based_on"]["observations"] == []
    assert metadata["provenance"]["derivation"] == "literature-derived"
    assert metadata["provenance"]["local_empirical_support"] is False
    source = metadata["provenance"]["idea_sources"][0]
    assert source["evidence"][0]["paper_id"] == paper_id
    assert source["evidence"][0]["claim_ids"] == ["C01"]
    assert "XIDEA-0001" in body
    assert any("local empirical support" in warning for warning in metadata["provenance"]["warnings"])
    assert any("novelty: unchecked" in warning for warning in metadata["provenance"]["warnings"])


def test_unknown_idea_is_rejected(rf_env, tmp_path):
    project, _ = _project_with_idea(rf_env, tmp_path)
    with pytest.raises(ResearchFlowError, match="Broken evidence reference XIDEA-9999"):
        add_hypothesis(project, "TEST", "TEST", ideas=["XIDEA-9999"])


def test_idea_or_matrix_change_makes_hypothesis_provenance_stale(rf_env, tmp_path):
    project, _ = _project_with_idea(rf_env, tmp_path)
    hypothesis_id = add_hypothesis(project, "TEST", "TEST", ideas=["XIDEA-0001"])
    metadata, _ = show_record(project, hypothesis_id)
    assert hypothesis_provenance_status(project, metadata)["stale"] is False
    matrix = LiteratureMatrixStore(project)
    record = matrix.load()
    record["ideas"][0]["mechanism"] = "TEST changed mechanism"
    matrix.replace(record)
    status = hypothesis_provenance_status(project, metadata)
    assert status["stale"] is True
    assert status["idea_sources"][0]["idea_changed"] is True
    assert any("requires review" in warning for warning in status["warnings"])


def test_hypothesis_cli_reports_novelty_and_empirical_boundary(rf_env, tmp_path, capsys):
    from researchflow.cli import main

    project, _ = _project_with_idea(rf_env, tmp_path)
    assert main([
        "hypothesis", "new", "--title", "TEST", "--statement", "TEST",
        "--ideas", "XIDEA-0001", "--falsification", "TEST",
    ]) == 0
    output = capsys.readouterr().out
    assert "novelty: unchecked" in output
    assert "local empirical support has not been established" in output
    assert project.root.exists()
