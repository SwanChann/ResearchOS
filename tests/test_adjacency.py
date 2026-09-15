from __future__ import annotations

from pathlib import Path

import pytest

from researchflow.adjacency import PaperAdjacencyStore
from researchflow.concepts import ConceptStore
from researchflow.config import research_home
from researchflow.corpus_gap import CorpusStore, GapStore, V2_COVERAGE_RULES
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


def _v2_tuple(subject_type: str, subject_key: str, relation: str, object_type: str, object_key: str, number: int) -> dict:
    value = _tuple(subject_type, subject_key, relation, object_type, object_key, number)
    value["assertion"] = f"TEST assertion {number}; MOCK evidence only."
    return value


def _v2_coverage(tuples: list[dict]) -> dict:
    coverage = {}
    for name, rule in V2_COVERAGE_RULES.items():
        found = any(
            item["relation"] in rule["relations"]
            or item["subject"]["type"] in rule["types"]
            or item["object"]["type"] in rule["types"]
            for item in tuples
        )
        coverage[name] = {
            "status": "covered" if found else "not_reported",
            "rationale": f"TEST {name} {'has MOCK tuple evidence' if found else 'is not reported in this fixture'}.",
        }
    return coverage


def _add_accepted_concept(project: ResearchProject, request: Path, payload: dict) -> str:
    write_yaml(request, payload)
    concept = ConceptStore(project).add_file(request)["concept"]
    ConceptStore(project).review(
        concept["id"], decision="accepted", reviewer="human:test",
        rationale="TEST normalization checked for this MOCK vocabulary.",
    )
    return concept["id"]


def _semantic_fixture(rf_env) -> tuple[ResearchProject, dict, list[str]]:
    add_project("semantic-toy", rf_env["repo"])
    project = ResearchProject.open("semantic-toy")
    matrix = LiteratureMatrixStore(project)
    matrix.initialize("TEST semantic matrix", "TEST / MOCK only")
    papers = []
    for number in range(41, 44):
        paper_id = _paper(project, number)
        papers.append(paper_id)
        axes = matrix.load()["axes"]
        matrix.add_entry({
            "paper_id": paper_id, "role": "TEST", "decision": "central", "next_checks": [],
            "cells": {axis["id"]: {"status": "not_reported", "text": "TEST", "evidence": []} for axis in axes},
        })
    scope = project.root / ".research/semantic-scope.yaml"
    write_yaml(scope, {
        "research_area": "TEST semantic navigation", "application_context": "TEST inspection",
        "included_years": [2026], "inclusion_rules": ["TEST verified"], "exclusion_rules": ["none"],
    })
    corpus = CorpusStore(project).create(
        title="TEST semantic Corpus", matrix_id="LITMATRIX-0001", scope_file=scope,
    )["corpus"]

    concepts = project.root / ".research"
    _add_accepted_concept(project, concepts / "task-concept.yaml", {
        "type": "Task", "canonical_key": "task/vln", "label": "TEST VLN",
        "aliases": ["task/continuous-vln", "task/instruction-navigation"],
        "broader_key": None, "related_keys": [], "rationale": "TEST aliases denote the same MOCK task.",
        "source": {"kind": "human", "name": "human:test", "version": "TEST-v1"},
    })
    _add_accepted_concept(project, concepts / "method-family.yaml", {
        "type": "Method", "canonical_key": "method/family/agentic-nav", "label": "TEST agentic navigation family",
        "aliases": [], "broader_key": None, "related_keys": [], "rationale": "TEST MOCK family root.",
        "source": {"kind": "human", "name": "human:test", "version": "TEST-v1"},
    })
    for key in ("method/baseline-nav", "method/adaptive-nav"):
        _add_accepted_concept(project, concepts / f"{key.rsplit('/', 1)[-1]}.yaml", {
            "type": "Method", "canonical_key": key, "label": f"TEST {key}", "aliases": [],
            "broader_key": "method/family/agentic-nav", "related_keys": [],
            "rationale": "TEST method belongs to the MOCK agentic navigation family.",
            "source": {"kind": "human", "name": "human:test", "version": "TEST-v1"},
        })

    tuples_by_paper = [
        [
            _v2_tuple("Paper", "paper/baseline", "proposes", "Method", "method/baseline-nav", 101),
            _v2_tuple("Paper", "paper/baseline", "studies", "Problem", "problem/reliable-navigation", 102),
            _v2_tuple("Method", "method/baseline-nav", "uses_component", "Component", "component/base-policy", 103),
            _v2_tuple("Method", "method/baseline-nav", "trained_with", "TrainingSignal", "training/imitation", 104),
            _v2_tuple("Method", "method/baseline-nav", "evaluated_on", "Task", "task/continuous-vln", 105),
            _v2_tuple("Method", "method/baseline-nav", "uses_dataset", "Dataset", "dataset/mock-a", 106),
            _v2_tuple("Result", "result/baseline-success", "measured_by", "Metric", "metric/success", 107),
            _v2_tuple("Method", "method/baseline-nav", "reports_result", "Result", "result/baseline-success", 108),
            _v2_tuple("Method", "method/baseline-nav", "assumes", "Assumption", "assumption/static-world", 109),
            _v2_tuple("Method", "method/baseline-nav", "limited_by", "Limitation", "limitation/failure-recovery", 110),
            _v2_tuple("Method", "method/baseline-nav", "fails_under", "FailureCondition", "failure/dynamic-obstacle", 111),
            _v2_tuple("Method", "method/baseline-nav", "compared_with", "Method", "method/prior", 112),
        ],
        [
            _v2_tuple("Paper", "paper/adaptive", "proposes", "Method", "method/adaptive-nav", 121),
            _v2_tuple("Paper", "paper/adaptive", "studies", "Problem", "problem/reliable-navigation", 122),
            _v2_tuple("Method", "method/adaptive-nav", "uses_component", "Component", "component/recovery-policy", 123),
            _v2_tuple("Method", "method/adaptive-nav", "uses_feedback", "Feedback", "feedback/execution", 124),
            _v2_tuple("Method", "method/adaptive-nav", "evaluated_on", "Task", "task/instruction-navigation", 125),
            _v2_tuple("Method", "method/adaptive-nav", "uses_dataset", "Dataset", "dataset/mock-b", 126),
            _v2_tuple("Result", "result/adaptive-success", "measured_by", "Metric", "metric/recovery", 127),
            _v2_tuple("Method", "method/adaptive-nav", "reports_result", "Result", "result/adaptive-success", 128),
            _v2_tuple("Method", "method/adaptive-nav", "assumes", "Assumption", "assumption/execution-feedback", 129),
            _v2_tuple("Method", "method/adaptive-nav", "limited_by", "Limitation", "limitation/mock-scale", 130),
            _v2_tuple("Method", "method/adaptive-nav", "extends", "Method", "method/baseline-nav", 131),
            _v2_tuple("Method", "method/adaptive-nav", "addresses", "Limitation", "limitation/failure-recovery", 132),
        ],
        [
            _v2_tuple("Paper", "paper/unrelated", "proposes", "Method", "method/unrelated", 141),
            _v2_tuple("Paper", "paper/unrelated", "studies", "Problem", "problem/object-counting", 142),
            _v2_tuple("Method", "method/unrelated", "uses_component", "Component", "component/counter", 143),
            _v2_tuple("Method", "method/unrelated", "evaluated_on", "Task", "task/object-counting", 144),
            _v2_tuple("Method", "method/unrelated", "reports_result", "Result", "result/counting", 145),
            _v2_tuple("Method", "method/unrelated", "limited_by", "Limitation", "limitation/lighting", 146),
        ],
    ]
    corpora = CorpusStore(project)
    for paper, tuples in zip(corpus["papers"], tuples_by_paper, strict=True):
        request = project.root / ".research" / f"v2-{paper['id']}.yaml"
        write_yaml(request, {
            "schema_version": 2, "corpus_id": corpus["id"], "paper_id": paper["id"],
            "paper_fingerprint": paper["source_fingerprint"],
            "extractor": {"kind": "agent", "name": "TEST", "version": "v2"},
            "coverage": _v2_coverage(tuples), "tuples": tuples,
        })
        assert corpora.preflight_extraction(request)["valid"] is True
        corpora.add_extraction(request)
        corpora.review_extraction(
            corpus["id"], paper["id"], decision="accepted", reviewer="human:test",
            rationale="TEST V2 extraction checked against MOCK claims.",
        )
    return project, corpus, papers


def test_v2_semantic_adjacency_packet_and_evaluation(rf_env):
    project, corpus, papers = _semantic_fixture(rf_env)
    status = CorpusStore(project).extraction_status(corpus["id"])
    assert {item["schema_version"] for item in status["extractions"]} == {2}
    store = PaperAdjacencyStore(project)
    structural = store.build(corpus["id"], mode="structural", details=True, dry_run=True)
    semantic = store.build(corpus["id"], mode="semantic", details=True, dry_run=True)
    assert semantic["candidate_count"] > structural["candidate_count"]
    triples = {(item["from"], item["relation"], item["to"]) for item in semantic["candidates"]}
    assert (papers[0], "same_problem", papers[1]) in triples
    assert (papers[0], "same_method_family", papers[1]) in triples
    assert (papers[1], "extends_method", papers[0]) in triples
    assert (papers[1], "addresses_limitation", papers[0]) in triples

    packet = store.packet(corpus["id"], top_k=3)
    assert packet["pairs"][0]["from"] == papers[0]
    assert packet["pairs"][0]["to"] == papers[1]
    assert packet["pairs"][0]["papers"][0]["extraction_schema_version"] == 2
    assert packet["vocabulary_fingerprint"] == ConceptStore(project).fingerprint()

    benchmark = project.root / ".research/semantic-benchmark.yaml"
    benchmark_record = {
        "schema_version": 1, "benchmark_id": "test/semantic-v1", "corpus_id": corpus["id"],
        "corpus_fingerprint": corpus["corpus_fingerprint"],
        "rationale": "TEST benchmark for MOCK semantic relations.",
        "cases": [
            {"from": papers[0], "relation": "same_problem", "to": papers[1], "expected": True, "rationale": "TEST alias normalization."},
            {"from": papers[0], "relation": "same_method_family", "to": papers[1], "expected": True, "rationale": "TEST broader method family."},
            {"from": papers[1], "relation": "extends_method", "to": papers[0], "expected": True, "rationale": "TEST explicit extension."},
            {"from": papers[1], "relation": "addresses_limitation", "to": papers[0], "expected": True, "rationale": "TEST explicit limitation handling."},
            {"from": papers[0], "relation": "same_problem", "to": papers[2], "expected": False, "rationale": "TEST hard negative."},
        ],
    }
    from researchflow.corpus_gap import canonical_hash
    benchmark_record["review"] = {
        "reviewer": "human:test",
        "reviewed_fingerprint": canonical_hash(benchmark_record),
        "rationale": "TEST cases reviewed against the MOCK fixture.",
        "reviewed_at": "2026-09-15T00:00:00+00:00",
    }
    write_yaml(benchmark, benchmark_record)
    result = store.evaluate(corpus["id"], benchmark, mode="semantic")
    assert result["confusion"] == {"tp": 4, "fp": 0, "fn": 0, "tn": 1}
    assert result["metrics"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    changed = read_yaml(benchmark)
    changed["cases"][0]["rationale"] = "TEST benchmark changed after review."
    write_yaml(benchmark, changed)
    with pytest.raises(ResearchFlowError, match="review fingerprint is stale"):
        store.evaluate(corpus["id"], benchmark, mode="semantic")


def test_v2_coverage_and_concept_human_gates(rf_env):
    project, corpus, papers = _fixture(rf_env)
    corpora = CorpusStore(project)
    v1_scaffold = project.root / ".research/scaffold-v1.yaml"
    v2_scaffold = project.root / ".research/scaffold-v2.yaml"
    corpora.scaffold_extraction(corpus["id"], papers[0], v1_scaffold)
    corpora.scaffold_extraction_v2(corpus["id"], papers[0], v2_scaffold)
    assert read_yaml(v1_scaffold).get("schema_version") is None
    assert corpora.preflight_extraction(v1_scaffold)["valid"] is True
    assert read_yaml(v2_scaffold)["schema_version"] == 2
    assert preflight(project, "corpus-extraction-v2", v2_scaffold)["valid"] is True

    concept_request = project.root / ".research/concept-gate.yaml"
    write_yaml(concept_request, {
        "type": "Task", "canonical_key": "task/test", "label": "TEST task", "aliases": [],
        "broader_key": None, "related_keys": [], "rationale": "TEST normalization.",
        "source": {"kind": "agent", "name": "TEST", "version": "v1"},
    })
    concept = ConceptStore(project).add_file(concept_request)["concept"]
    with pytest.raises(ResearchFlowError, match="human"):
        ConceptStore(project).review(
            concept["id"], decision="accepted", reviewer="agent:test", rationale="TEST",
        )
    ConceptStore(project).review(
        concept["id"], decision="accepted", reviewer="human:test", rationale="TEST normalization reviewed.",
    )
    assert ConceptStore(project).resolve("Task", "task/test")["concept_id"] == concept["id"]

    child_request = project.root / ".research/concept-child.yaml"
    write_yaml(child_request, {
        "type": "Task", "canonical_key": "task/test-child", "label": "TEST child", "aliases": [],
        "broader_key": "task/missing-parent", "related_keys": [], "rationale": "TEST missing parent gate.",
        "source": {"kind": "agent", "name": "TEST", "version": "v1"},
    })
    child = ConceptStore(project).add_file(child_request)["concept"]
    with pytest.raises(ResearchFlowError, match="unavailable accepted broader key"):
        ConceptStore(project).review(
            child["id"], decision="accepted", reviewer="human:test", rationale="TEST should fail closed.",
        )

    request = project.root / ".research/invalid-v2.yaml"
    tuples = [_v2_tuple("Paper", "paper/test", "proposes", "Method", "method/test", 201)]
    coverage = _v2_coverage(tuples)
    coverage["results"] = {"status": "covered", "rationale": "TEST invalid claim."}
    write_yaml(request, {
        "schema_version": 2, "corpus_id": corpus["id"], "paper_id": papers[0],
        "paper_fingerprint": corpus["papers"][0]["source_fingerprint"],
        "extractor": {"kind": "agent", "name": "TEST", "version": "v2"},
        "coverage": coverage, "tuples": tuples,
    })
    with pytest.raises(ResearchFlowError, match="coverage.results"):
        CorpusStore(project).preflight_extraction(request)
