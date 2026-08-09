from researchflow.project import ResearchProject, add_project


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

