from __future__ import annotations

from pathlib import Path

import pytest

from researchflow.adjacency import PaperAdjacencyStore
from researchflow.config import research_home
from researchflow.corpus_gap import CorpusStore, GapStore
from researchflow.errors import ResearchFlowError
from researchflow.evidence_graph import EvidenceGraphStore, ProblemStore
from researchflow.ids import allocate_id, validate_id
from researchflow.io import atomic_text, markdown_record, read_yaml, write_yaml
from researchflow.literature import LiteratureMatrixStore
from researchflow.project import ResearchProject, add_project
from researchflow.scaffold import paper_adjacency_scaffold, preflight


def _paper(project: ResearchProject, number: int) -> str:
    paper_id = allocate_id(research_home(), "PAPER")
    fingerprint = f"{number:064x}"[-64:].upper()
    metadata = {
        "id": paper_id, "title": f"TEST adjacency paper {number}", "authors": ["TEST Author"],
        "venue": "TEST", "year": 2026,
        "source": {"url": f"https://example.invalid/{number}", "local_pdf": None, "document": {
            "sha256": fingerprint, "version": "TEST-v1", "page_count": 3,
            "citation_basis": "pdf_page", "inspected_at": "2026-09-15T00:00:00+00:00",
        }},
        "tags": ["TEST"], "methods": ["TEST-method"], "status": "verified",
        "core_operator": "TEST", "primary_logic": "TEST", "verified_at": "2026-09-15T00:00:00+00:00",
    }
    body = "# TEST\n\n## Verified Claims\n\nC01 TEST at p. 1.\n\nC02 TEST at p. 2.\n\n## Idea Seeds\n\nIDEA-01\n"
    atomic_text(project.root / "evidence/papers/analysis" / f"{paper_id}.md", markdown_record(metadata, body))
    return paper_id


def _tuple(subject_type: str, subject_key: str, relation: str, object_type: str, object_key: str, number: int) -> dict:
    return {
        "subject": {"type": subject_type, "key": subject_key},
        "relation": relation,
        "object": {"type": object_type, "key": object_key},
        "evidence": {
            "paper_claim_ids": ["C01" if number % 2 else "C02"],
            "locators": [{"kind": "page", "value": str(1 if number % 2 else 2)}],
            "exact_text_sha256": f"{number + 100:064x}"[-64:],
        },
        "epistemic_status": "paper_reported",
    }


def _fixture(rf_env) -> tuple[ResearchProject, dict, list[str]]:
    add_project("adjacency-toy", rf_env["repo"])
    project = ResearchProject.open("adjacency-toy")
    matrix = LiteratureMatrixStore(project)
    matrix.initialize("TEST adjacency matrix", "TEST / MOCK only")
    papers = []
    for number in range(1, 4):
        paper_id = _paper(project, number)
        papers.append(paper_id)
        axes = matrix.load()["axes"]
        matrix.add_entry({
            "paper_id": paper_id, "role": "TEST", "decision": "central", "next_checks": [],
            "cells": {axis["id"]: {"status": "not_reported", "text": "TEST", "evidence": []} for axis in axes},
        })
    scope = project.root / ".research/adjacency-scope.yaml"
    write_yaml(scope, {
        "research_area": "TEST navigation", "application_context": "TEST inspection",
        "included_years": [2026], "inclusion_rules": ["TEST verified"], "exclusion_rules": ["none"],
    })
    corpora = CorpusStore(project)
    corpus = corpora.create(title="TEST adjacency Corpus", matrix_id="LITMATRIX-0001", scope_file=scope)["corpus"]
    for number, paper in enumerate(corpus["papers"], 1):
        method = "method/shared" if number < 3 else "method/other"
        dataset = "dataset/shared" if number < 3 else "dataset/other"
        tuples = [
            _tuple("Paper", f"paper/{number}", "proposes", "Method", method, number * 10 + 1),
            _tuple("Method", method, "evaluated_on", "Task", "task/inspection", number * 10 + 2),
            _tuple("Method", method, "uses_dataset", "Dataset", dataset, number * 10 + 3),
            _tuple("Method", method, "assumes", "Assumption", "assumption/static-scene", number * 10 + 4),
        ]
        if number == 1:
            tuples.append(_tuple("Method", method, "fails_under", "FailureCondition", "failure/dynamic-obstacle", 19))
        request = project.root / ".research" / f"adjacency-extract-{number}.yaml"
        write_yaml(request, {
            "corpus_id": corpus["id"], "paper_id": paper["id"],
            "paper_fingerprint": paper["source_fingerprint"],
            "extractor": {"kind": "agent", "name": "TEST", "version": "v1"},
            "tuples": tuples,
        })
        corpora.add_extraction(request)
        corpora.review_extraction(
            corpus["id"], paper["id"], decision="accepted", reviewer="human:test",
            rationale="TEST extraction checked against TEST claims.",
        )
    return project, corpus, papers


def test_structural_build_is_deterministic_explainable_and_idempotent(rf_env):
    project, corpus, papers = _fixture(rf_env)
    store = PaperAdjacencyStore(project)
    preview = store.build(corpus["id"], dry_run=True)
    assert preview["candidate_count"] == 9
    assert preview["relations"] == {
        "exposes_failure": 1,
        "same_evaluation": 1,
        "same_method_family": 1,
        "same_problem": 3,
        "shares_assumption": 3,
    }
    assert not store.path.exists()
    created = store.build(corpus["id"])
    assert created["created_edges"] == 9
    assert store.build(corpus["id"])["idempotent"] is True
    assert store.check()["valid"] is True
    edge = next(item for item in store.list() if item["relation"] == "same_method_family")
    assert validate_id(edge["id"], "PADJ")
    assert edge["evidence"][0]["claim_ids"]
    assert edge["evidence"][0]["locators"]
    explained = store.explain(papers[0], papers[1])
    assert {item["relation"] for item in explained["edges"]} >= {"same_problem", "same_method_family", "same_evaluation"}


def test_human_gate_neighbors_staleness_and_graph_promotion(rf_env):
    project, corpus, papers = _fixture(rf_env)
    store = PaperAdjacencyStore(project)
    store.build(corpus["id"])
    edge = next(item for item in store.list() if item["relation"] == "same_method_family")
    with pytest.raises(ResearchFlowError, match="human"):
        store.review(edge["id"], decision="accepted", reviewer="agent:test", rationale="TEST")
    store.review(edge["id"], decision="accepted", reviewer="human:Modes", rationale="TEST relation checked.")
    neighbors = store.neighbors(papers[0])
    assert neighbors["count"] == 1
    assert neighbors["neighbors"][0]["edge_id"] == edge["id"]
    promoted = store.promote(edge["id"])
    assert promoted["created"] is True
    assert EvidenceGraphStore(project).check()["valid"] is True

    paper_path = project.root / "evidence/papers/analysis" / f"{papers[0]}.md"
    paper_path.write_text(paper_path.read_text(encoding="utf-8").replace("TEST adjacency paper 1", "Changed TEST paper"), encoding="utf-8")
    assert store.show(edge["id"])["current"] is False
    assert store.neighbors(papers[0])["count"] == 0
    assert EvidenceGraphStore(project).check()["valid"] is False


def test_accepted_extraction_change_invalidates_adjacency(rf_env):
    project, corpus, _ = _fixture(rf_env)
    store = PaperAdjacencyStore(project)
    store.build(corpus["id"])
    edge = next(item for item in store.list() if item["relation"] == "same_method_family")
    store.review(edge["id"], decision="accepted", reviewer="human:Modes", rationale="TEST relation checked.")

    extraction = store.corpora.extraction_root / corpus["id"] / f"{edge['from']}.yaml"
    record = read_yaml(extraction)
    record["tuples"][0]["object"]["key"] = "method/changed-after-review"
    write_yaml(extraction, record)
    shown = store.show(edge["id"])
    assert shown["current"] is False
    assert any("human-accepted extraction" in issue for issue in shown["issues"])


def test_export_and_cli_contract(rf_env):
    project, corpus, _ = _fixture(rf_env)
    store = PaperAdjacencyStore(project)
    store.build(corpus["id"])
    dot = project.root / ".research/paper-adjacency/graph.dot"
    preview = store.export(dot, format="dot", dry_run=True)
    assert preview["dry_run"] is True and not dot.exists()
    store.export(dot, format="dot")
    assert "same_problem" in dot.read_text(encoding="utf-8")
    with pytest.raises(ResearchFlowError, match="inside the project workspace"):
        store.export(project.root.parent / "escaped-adjacency.json")


def test_manual_scaffold_preflight_import_and_review(rf_env):
    project, corpus, papers = _fixture(rf_env)
    request = project.root / ".research/manual-adjacency.yaml"
    paper_adjacency_scaffold(project, corpus["id"], papers[1], papers[0], request)
    preview = preflight(project, "paper-adjacency", request)
    assert preview["valid"] is True
    store = PaperAdjacencyStore(project)
    dry_run = store.add_file(request, dry_run=True)
    assert dry_run["dry_run"] is True and not store.path.exists()
    created = store.add_file(request)
    assert created["created"] is True
    edge = created["edge"]
    assert edge["from"] == min(papers[0], papers[1])
    assert store.add_file(request)["idempotent"] is True
    store.review(edge["id"], decision="accepted", reviewer="human:Modes", rationale="TEST manual relation inspected.")
    assert store.show(edge["id"])["usable_for_gap"] is True


def test_accepted_adjacency_can_create_and_close_a_gap_candidate(rf_env):
    project, corpus, papers = _fixture(rf_env)
    store = PaperAdjacencyStore(project)
    store.build(corpus["id"])
    failure = next(item for item in store.list() if item["relation"] == "exposes_failure")
    store.review(failure["id"], decision="accepted", reviewer="human:Modes", rationale="TEST failure relation checked.")

    problem_request = project.root / ".research/adjacency-problem.yaml"
    write_yaml(problem_request, {
        "title": "TEST adjacency problem", "objective": "TEST the adjacency Gap path.",
        "scope": "TEST / MOCK only", "constraints": ["No external execution"],
        "application_context": "TEST inspection", "status": "active", "supersedes": None,
    })
    problem = ProblemStore(project).add_file(problem_request)["problem"]["id"]
    motifs = project.root / ".research/adjacency-motifs.yaml"
    scores = {
        "novelty": {"value": 0.5, "kind": "heuristic", "algorithm": "TEST-v1"},
        "feasibility": {"value": 0.5, "kind": "heuristic", "algorithm": "TEST-v1"},
    }
    write_yaml(motifs, {
        "schema_version": 1, "version": "paper-adjacency-motif-v1", "rules": [
            {
                "id": "UNHANDLED_FAILURE", "motif": "adjacency_boundary_gap", "problem_id": problem,
                "title": "TEST unhandled failure", "statement": "A reviewed failure relation has no reviewed addressing relation.",
                "mechanism_missing": "TEST recovery", "remaining_scope": "TEST shared method only",
                "boundary_conditions": ["TEST dynamic obstacle"], "falsification": "An accepted addresses_limitation relation exists.",
                "adjacency_match": {"relation": "exposes_failure"},
                "adjacency_absence_match": {"relation": "addresses_limitation"},
                "known_counterevidence": [], "scores": scores,
            },
            {
                "id": "TUPLE_WITH_MISSING_ADJACENCY", "motif": "adjacency_missing_relation", "problem_id": problem,
                "title": "TEST tuple-triggered missing relation", "statement": "A failure tuple has no reviewed addressing relation.",
                "mechanism_missing": "TEST recovery", "remaining_scope": "TEST shared method only",
                "boundary_conditions": ["TEST dynamic obstacle"], "falsification": "An accepted addresses_limitation relation exists.",
                "tuple_match": {"relation": "fails_under"},
                "adjacency_absence_match": {"relation": "addresses_limitation"},
                "known_counterevidence": [], "scores": scores,
            },
        ]})
    first = GapStore(project).detect(corpus["id"], motifs, test_only=True)
    assert len(first["candidate_gaps"]) == 2
    gaps = [GapStore(project).show(gap_id) for gap_id in first["candidate_gaps"]]
    gap = next(item for item in gaps if item["record"]["derivation"]["motif_id"] == "UNHANDLED_FAILURE")
    gap_id = gap["record"]["id"]
    assert gap["record"]["derivation"]["adjacency_ids"] == [failure["id"]]
    assert gap["content_current"] is True
    tuple_gap = next(item for item in gaps if item["record"]["derivation"]["motif_id"] == "TUPLE_WITH_MISSING_ADJACENCY")
    assert tuple_gap["record"]["derivation"]["adjacency_input_fingerprint"]

    addressing = project.root / ".research/addressing-adjacency.yaml"
    write_yaml(addressing, {
        "corpus_id": corpus["id"], "from": papers[1], "relation": "addresses_limitation", "to": papers[0],
        "directed": True, "dimensions": ["limitation"],
        "evidence": [
            {"paper_id": paper_id, "tuple_ids": [], "claim_ids": ["C01"], "locators": [{"kind": "page", "value": "1"}]}
            for paper_id in (papers[1], papers[0])
        ],
        "rationale": "TEST paper 2 addresses the bounded limitation reported by paper 1.",
        "score": {"structural": 0.0, "semantic": 0.8, "overall": 0.8, "basis": "TEST human semantic assessment"},
        "generator": {"kind": "human", "name": "human:Modes", "version": "TEST-v1"},
    })
    addressing_edge = store.add_file(addressing)["edge"]
    store.review(addressing_edge["id"], decision="accepted", reviewer="human:Modes", rationale="TEST addressing relation checked.")
    assert GapStore(project).show(gap_id)["content_current"] is False
    assert GapStore(project).show(tuple_gap["record"]["id"])["content_current"] is False
    second = GapStore(project).detect(corpus["id"], motifs, dry_run=True, test_only=True)
    assert second["candidate_count"] == 0
