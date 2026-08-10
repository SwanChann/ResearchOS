import pytest

from researchflow.errors import ResearchFlowError
from researchflow.io import markdown_record, read_markdown_record
from researchflow.project import ResearchProject, add_project
from researchflow.doctor import run_doctor


def test_paper_and_repo_evidence_are_searchable(rf_env, tmp_path):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% TEST FIXTURE\n")
    paper = project.evidence.add_paper(pdf, "Toy Navigation", year=2026, tags=["navigation"])
    repo = project.evidence.add_repo("ToyCode", "abc123", local=rf_env["repo"], related_papers=[paper], tags=["navigation"])
    assert project.evidence.show(paper)["metadata"]["status"] == "unread"
    assert project.evidence.show(repo)["pin"]["commit"] == "abc123"
    assert {item["id"] for item in project.evidence.search("navigation")} == {paper, repo}
    duplicate_check = next(check for check in run_doctor("toy") if check.name == "duplicate record IDs")
    assert duplicate_check.ok, "paper PDF and analysis are one entity, not duplicate IDs"


def test_verify_paper_requires_deep_read_contract_and_updates_index(rf_env, tmp_path):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% TEST FIXTURE\n")
    paper = project.evidence.add_paper(pdf, "Toy Navigation", year=2026, tags=["navigation"])

    with pytest.raises(ResearchFlowError, match="unread placeholder"):
        project.evidence.verify_paper(
            paper,
            sha256="A" * 64,
            source_version="TEST-v1",
            page_count=2,
            core_operator="TEST operator",
            primary_logic="TEST logic",
            methods=["TEST method"],
        )

    path = project.root / "evidence" / "papers" / "analysis" / f"{paper}.md"
    metadata, _ = read_markdown_record(path)
    body = """# Toy Navigation

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
        paper,
        sha256="a" * 64,
        source_version="TEST-v1",
        page_count=2,
        core_operator="TEST operator",
        primary_logic="TEST logic",
        methods=["TEST method", "TEST method"],
    )

    record = project.evidence.show(paper)["metadata"]
    assert record["status"] == "verified"
    assert record["source"]["document"]["sha256"] == "A" * 64
    assert record["source"]["document"]["citation_basis"] == "pdf_page"
    index = project.evidence.list("paper")[0]
    assert index["methods"] == ["TEST method"]
    assert index["status"] == "verified"
