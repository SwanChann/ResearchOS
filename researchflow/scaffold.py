from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import ResearchFlowError
from .evidence import DEEP_READ_BODY, EvidenceStore
from .io import atomic_text, markdown_record, read_markdown_record, write_yaml
from .literature import LiteratureMatrixStore
from .schema import validate_record


def _new_target(path: Path) -> Path:
    target = path.expanduser().resolve()
    if target.exists():
        raise ResearchFlowError(f"Scaffold target already exists: {target}")
    return target


def paper_analysis_scaffold(project, paper_id: str, output: Path) -> Path:
    target = _new_target(output)
    source = project.root / "evidence" / "papers" / "analysis" / f"{paper_id}.md"
    if not source.is_file():
        raise ResearchFlowError(f"Paper evidence not found: {paper_id}")
    metadata, _ = read_markdown_record(source)
    atomic_text(target, markdown_record(metadata, DEEP_READ_BODY.format(title=metadata["title"])))
    return target


def matrix_entry_scaffold(project, paper_id: str, output: Path) -> Path:
    target = _new_target(output)
    matrix = LiteratureMatrixStore(project).load()
    project.evidence.show(paper_id)
    write_yaml(target, {
        "paper_id": paper_id,
        "role": "Agent-generated draft; requires human review.",
        "decision": "supporting",
        "next_checks": ["Review every cell against the locked source fingerprint."],
        "cells": {
            axis["id"]: {
                "status": "not_reported",
                "text": "Agent-generated draft; determine explicitly from the verified source.",
                "evidence": [],
            } for axis in matrix["axes"]
        },
    })
    return target


def synthesis_idea_scaffold(project, output: Path) -> Path:
    target = _new_target(output)
    matrix = LiteratureMatrixStore(project).load()
    atomic_text(target, "# Agent-generated draft. Fill evidence refs and run rf preflight matrix-synthesis before writing.\n" + __import__("yaml").safe_dump({
        "matrix_id": matrix["id"], "mode": "upsert",
        "syntheses": [{
            "id": "SYN-001", "statement": "DRAFT", "strength": "analyst_inference",
            "evidence": [], "caveat": "DRAFT; requires human semantic review.",
        }],
        "ideas": [{
            "id": "XIDEA-001", "title": "DRAFT", "trigger": "DRAFT", "mechanism": "DRAFT",
            "falsification": "DRAFT", "risks": "DRAFT", "novelty": "unchecked", "evidence": [],
        }],
    }, sort_keys=False, allow_unicode=True))
    return target


def artifact_scaffold(output: Path, artifact_path: Path, title: str, artifact_type: str) -> Path:
    target = _new_target(output)
    write_yaml(target, {
        "agent_generated_draft": True,
        "path": str(artifact_path), "title": title, "type": artifact_type,
        "status": "draft", "authority": "researchflow_workspace",
        "derived_from": [], "evidence": [], "schema": None, "version": None,
    })
    return target


def problem_scaffold(output: Path) -> Path:
    target = _new_target(output)
    write_yaml(target, {
        "title": "DRAFT research problem",
        "objective": "DRAFT: state the observable objective.",
        "scope": "DRAFT: state the included and excluded setting.",
        "constraints": ["DRAFT: state a real resource or deployment constraint."],
        "application_context": "DRAFT application context",
        "status": "active",
        "supersedes": None,
        "body": "Agent-generated draft; human review is required before import.",
    })
    return target


def claim_scaffold(output: Path) -> Path:
    target = _new_target(output)
    write_yaml(target, {
        "title": "DRAFT bounded claim",
        "statement": "DRAFT: state only what the registered Finding supports.",
        "scope": {
            "datasets": ["DRAFT-dataset"],
            "platforms": ["DRAFT-platform"],
            "seeds": [0],
            "conditions": ["DRAFT-condition"],
        },
        "qualifiers": ["Agent-generated draft; semantic review is required."],
        "supporting_findings": ["OBS-0000"],
        "counter_findings": [],
        "metric_evidence": [{
            "run_id": "RUN-000000",
            "artifact_id": "ARTIFACT-0000",
            "artifact_sha256": "0" * 64,
            "json_pointer": "/metrics/replace_me",
            "metric_id": "replace_me",
            "value": 0,
            "unit": "replace_me",
        }],
        "status": "draft",
        "supersedes": None,
        "body": "Agent-generated draft; structural checks do not establish scientific truth.",
    })
    return target


def graph_review_scaffold(project, claim_id: str, output: Path) -> Path:
    target = _new_target(output)
    from .evidence_graph import EvidenceGraphStore
    graph = EvidenceGraphStore(project)
    view = graph.claim_view(claim_id)
    write_yaml(target, {
        "target": claim_id,
        "target_fingerprint": view["claim_fingerprint"],
        "reviewer": "DRAFT-reviewer",
        "semantic_review": {
            "status": "unavailable",
            "rationale": "DRAFT: inspect the Claim, Findings, and falsification boundary.",
            "experiment_falsifiable": "unavailable",
            "claim_within_findings": "unavailable",
        },
        "fidelity_review": {
            "status": "pending", "failures": [],
            "rationale": "DRAFT: record M1-M5 fidelity status or leave explicitly pending.",
        },
        "provenance": {
            "provider": "manual", "model": "none", "prompt_version": "graph-review-v1",
            "input_fingerprint": graph.review_input_fingerprint(claim_id),
        },
    })
    return target


def paper_adjacency_scaffold(project, corpus_id: str, source: str, target_id: str, output: Path) -> Path:
    target = _new_target(output)
    from .corpus_gap import CorpusStore
    corpus = CorpusStore(project).show(corpus_id)["record"]
    paper_ids = {item["id"] for item in corpus["papers"]}
    if source not in paper_ids or target_id not in paper_ids or source == target_id:
        raise ResearchFlowError("Adjacency scaffold needs two distinct Papers from the selected Corpus.")
    write_yaml(target, {
        "corpus_id": corpus_id,
        "from": source,
        "relation": "same_problem",
        "to": target_id,
        "directed": False,
        "dimensions": ["problem"],
        "evidence": [
            {"paper_id": paper_id, "tuple_ids": [], "claim_ids": ["C01"], "locators": [{"kind": "page", "value": "1"}]}
            for paper_id in (source, target_id)
        ],
        "rationale": "DRAFT: explain the exact relation and its boundary.",
        "score": {"structural": 0.0, "semantic": None, "overall": 0.0, "basis": "DRAFT: no score is evidence of novelty."},
        "generator": {"kind": "agent_import", "name": "DRAFT", "version": "paper-adjacency-v1"},
    })
    return target


def preflight(project, kind: str, path: Path) -> dict[str, Any]:
    source = path.expanduser().resolve()
    if kind == "paper-analysis":
        metadata, body = read_markdown_record(source)
        validate_record("paper", metadata)
        EvidenceStore._validate_deep_read(body)
        return {
            "valid": True, "kind": kind,
            "meaning": "Paper analysis contract passes; interpretation, reproduction, and scientific claims remain unestablished.",
        }
    if kind == "matrix-entry":
        return LiteratureMatrixStore(project).preflight_entry_file(source)
    if kind == "matrix-synthesis":
        return LiteratureMatrixStore(project).preflight_synthesis_file(source)
    if kind == "artifact":
        return __import__("researchflow.artifact", fromlist=["ArtifactStore"]).ArtifactStore(project).preflight_request(source)
    if kind == "problem":
        return __import__("researchflow.evidence_graph", fromlist=["ProblemStore"]).ProblemStore(project).preflight(source)
    if kind == "claim":
        return __import__("researchflow.evidence_graph", fromlist=["ClaimStore"]).ClaimStore(project).preflight(source)
    if kind == "corpus-extraction":
        return __import__("researchflow.corpus_gap", fromlist=["CorpusStore"]).CorpusStore(project).preflight_extraction(source)
    if kind == "paper-adjacency":
        return __import__("researchflow.adjacency", fromlist=["PaperAdjacencyStore"]).PaperAdjacencyStore(project).preflight(source)
    if kind == "graph-review":
        from .evidence_graph import EvidenceGraphStore
        request = __import__("researchflow.io", fromlist=["read_yaml"]).read_yaml(source)
        validate_record("evidence_graph_review_request", request)
        graph = EvidenceGraphStore(project)
        if request["target_fingerprint"] != graph.claim_view(request["target"])["claim_fingerprint"]:
            raise ResearchFlowError("Graph review target fingerprint is stale.")
        if request["provenance"]["input_fingerprint"] != graph.review_input_fingerprint(request["target"]):
            raise ResearchFlowError("Graph review input fingerprint is stale.")
        return {
            "valid": True, "kind": kind, "target": request["target"],
            "meaning": "The review envelope is current; import still reruns L1 and fails closed.",
        }
    raise ResearchFlowError(f"Unknown scaffold preflight kind: {kind}")
