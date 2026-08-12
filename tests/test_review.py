from pathlib import Path

from researchflow.io import markdown_record, read_markdown_record
from researchflow.literature import GENERIC_AXES, LiteratureMatrixStore
from researchflow.knowledge import KnowledgeStore
from researchflow.project import ResearchProject, add_project
from researchflow.review import add_matrix_review, add_paper_review, matrix_review_status


def _verified_paper(project: ResearchProject, tmp_path: Path) -> str:
    pdf = tmp_path / "review.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% TEST\n")
    paper_id = project.evidence.add_paper(pdf, "Review TEST", authors=["Fixture"], year=2026)
    path = project.root / "evidence" / "papers" / "analysis" / f"{paper_id}.md"
    metadata, _ = read_markdown_record(path)
    body = """# TEST

## Source Snapshot
TEST source.

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
    return paper_id


def _entry(paper_id: str) -> dict:
    return {
        "paper_id": paper_id, "role": "TEST", "decision": "central", "next_checks": [],
        "cells": {
            axis["id"]: {
                "status": "supported", "text": "TEST",
                "evidence": [{"pages": "p. 2", "claim_ids": ["C01"], "locator": "TEST"}],
            } for axis in GENERIC_AXES
        },
    }


def test_source_verification_and_human_review_are_separate_and_bounded(rf_env, tmp_path):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    paper_id = _verified_paper(project, tmp_path)
    initial = project.evidence.show(paper_id)["verification_status"]
    assert initial["source_verified"] is True
    assert initial["fingerprint_verified"] is True
    assert initial["human_reviewed"] is False
    assert initial["semantic_review_pending"] is True
    assert initial["reproduction_unverified"] is True
    assert initial["scientific_claim_unestablished"] is True

    result = add_paper_review(
        project, paper_id, reviewer="Human TEST", decision="accepted",
        scope="Claim-to-source interpretation only", notes="TEST fixture",
    )
    assert result["verification"]["human_reviewed"] is True
    current = project.evidence.show(paper_id)["verification_status"]
    assert current["reviews"][0]["stale"] is False
    assert current["reproduction_unverified"] is True
    assert current["scientific_claim_unestablished"] is True


def test_source_fingerprint_change_makes_paper_review_stale(rf_env, tmp_path):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    paper_id = _verified_paper(project, tmp_path)
    add_paper_review(project, paper_id, reviewer="Human TEST", decision="accepted", scope="TEST scope")
    project.evidence.verify_paper(
        paper_id, sha256="B" * 64, source_version="TEST-v2", page_count=3,
        core_operator="TEST", primary_logic="TEST", methods=["TEST"],
    )
    status = project.evidence.show(paper_id)["verification_status"]
    assert status["human_reviewed"] is False
    assert status["semantic_review_pending"] is True
    assert status["stale_reviews"] == 1
    assert status["reviews"][0]["stale"] is True
    paper_entry = next(item for item in KnowledgeStore(project).inventory() if item["id"] == paper_id)
    assert "stale" in paper_entry["labels"]


def test_matrix_content_change_makes_review_stale(rf_env, tmp_path):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    paper_id = _verified_paper(project, tmp_path)
    matrix = LiteratureMatrixStore(project)
    matrix.initialize("TEST", "TEST")
    matrix.add_entry(_entry(paper_id))
    add_matrix_review(matrix, reviewer="Human TEST", decision="accepted", scope="Cross-paper interpretation")
    assert matrix_review_status(matrix.load())["human_reviewed"] is True
    record = matrix.load()
    record["papers"][0]["role"] = "TEST changed role"
    matrix.replace(record)
    status = matrix_review_status(matrix.load())
    assert status["human_reviewed"] is False
    assert status["stale_reviews"] == 1


def test_review_cli_output_never_claims_reproduction_or_scientific_establishment(rf_env, tmp_path, capsys):
    from researchflow.cli import main

    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    project = ResearchProject.open("toy")
    paper_id = _verified_paper(project, tmp_path)
    assert main([
        "evidence", "paper", "review", paper_id, "--reviewer", "Human TEST",
        "--decision", "accepted", "--scope", "TEST scope",
    ]) == 0
    output = capsys.readouterr().out
    assert "reproduction_unverified: true" in output
    assert "scientific_claim_unestablished: true" in output
