from __future__ import annotations

import json
from pathlib import Path

import pytest

from researchflow.artifact import ArtifactStore
from researchflow.config import research_home
import researchflow.corpus_gap as corpus_gap_module
from researchflow.corpus_gap import CorpusStore, GapStore
from researchflow.errors import ResearchFlowError
from researchflow.evidence_graph import ClaimStore, EvidenceGraphStore, ProblemStore
from researchflow.ids import allocate_id
from researchflow.io import atomic_text, markdown_record, read_markdown_record, read_yaml, write_yaml
from researchflow.literature import LiteratureMatrixStore
import researchflow.migration as migration_module
from researchflow.migration import migrate_corpus_gap_evidence_graph
from researchflow.project import ResearchProject, add_project
from researchflow.records import add_hypothesis, add_observation
from researchflow.snapshot import create_snapshot, restore_snapshot, verify_snapshot


def _paper(project: ResearchProject, number: int) -> str:
    paper_id = allocate_id(research_home(), "PAPER")
    fingerprint = f"{number:064x}"[-64:].upper()
    metadata = {
        "id": paper_id, "title": f"TEST paper {number}", "authors": ["Test Author"],
        "venue": "TEST", "year": 2026,
        "source": {"url": "https://example.invalid/test", "local_pdf": None, "document": {
            "sha256": fingerprint, "version": "TEST-v1", "page_count": 2,
            "citation_basis": "pdf_page", "inspected_at": "2026-09-05T00:00:00+00:00",
        }},
        "tags": ["TEST"], "methods": ["TEST-method"], "status": "verified",
        "core_operator": "TEST", "primary_logic": "TEST", "verified_at": "2026-09-05T00:00:00+00:00",
    }
    body = f"# TEST paper {number}\n\n## Verified Claims\n\nC01 is a TEST claim at p. 1.\n\n## Idea Seeds\n\nIDEA-01\n"
    atomic_text(project.root / "evidence/papers/analysis" / f"{paper_id}.md", markdown_record(metadata, body))
    return paper_id


def _matrix_with_papers(project: ResearchProject, count: int = 3) -> list[str]:
    matrix = LiteratureMatrixStore(project)
    matrix.initialize("TEST matrix", "TEST / MOCK only")
    papers = []
    for number in range(1, count + 1):
        paper_id = _paper(project, number)
        papers.append(paper_id)
        record = matrix.load()
        matrix.add_entry({
            "paper_id": paper_id, "role": "TEST", "decision": "central", "next_checks": [],
            "cells": {
                axis["id"]: {"status": "not_reported", "text": "TEST not reported", "evidence": []}
                for axis in record["axes"]
            },
        })
    return papers


def _problem(project: ResearchProject) -> str:
    request = project.root / ".research/problem.yaml"
    write_yaml(request, {
        "title": "TEST Problem", "objective": "Test the complete CorpusGap contract.",
        "scope": "TEST / MOCK only", "constraints": ["No external execution"],
        "application_context": "TEST inspection", "status": "active", "supersedes": None,
    })
    return ProblemStore(project).add_file(request)["problem"]["id"]


def _scope(path: Path) -> None:
    write_yaml(path, {
        "research_area": "TEST embodied navigation", "application_context": "TEST inspection",
        "included_years": [2026], "inclusion_rules": ["TEST source verified"],
        "exclusion_rules": ["No inaccessible source"],
    })


def _extraction(path: Path, corpus: dict, paper: dict, number: int) -> None:
    write_yaml(path, {
        "corpus_id": corpus["id"], "paper_id": paper["id"],
        "paper_fingerprint": paper["source_fingerprint"],
        "extractor": {"kind": "agent", "name": "TEST", "version": "v1"},
        "tuples": [{
            "subject": {"type": "Method", "key": f"method/test-{number}"},
            "relation": "limited_by",
            "object": {"type": "Limitation", "key": "limitation/no-recovery"},
            "evidence": {
                "paper_claim_ids": ["C01"], "locators": [{"kind": "page", "value": "1"}],
                "exact_text_sha256": f"{number + 20:064x}"[-64:],
            },
            "epistemic_status": "paper_reported",
        }],
    })


def _corpus_gap_fixture(rf_env) -> dict:
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    papers = _matrix_with_papers(project)
    problem = _problem(project)
    scope = project.root / ".research/corpus-scope.yaml"
    _scope(scope)
    corpora = CorpusStore(project)
    corpus = corpora.create(title="TEST Corpus", matrix_id="LITMATRIX-0001", scope_file=scope)["corpus"]
    for number, paper in enumerate(corpus["papers"], 1):
        request = project.root / ".research" / f"extract-{number}.yaml"
        _extraction(request, corpus, paper, number)
        corpora.add_extraction(request)
        corpora.review_extraction(
            corpus["id"], paper["id"], decision="accepted", reviewer="human:test",
            rationale="TEST source locations checked.",
        )
    motifs = project.root / ".research/motifs.yaml"
    write_yaml(motifs, {
        "schema_version": 1, "version": "motif-rules-v1", "rules": [{
            "id": "MISSING_RECOVERY", "motif": "missing_edge", "problem_id": problem,
            "title": "TEST recovery Gap", "statement": "TEST methods report a limitation without a recovery edge.",
            "mechanism_missing": "TEST recovery mechanism", "remaining_scope": "TEST bounded scope",
            "boundary_conditions": ["TEST condition"], "falsification": "Reject if a recovery edge is present.",
            "tuple_match": {"relation": "limited_by", "object_key": "limitation/no-recovery"},
            "absence_match": {"relation": "proposes", "object_key": "method/recovery"},
            "known_counterevidence": [{
                "ref": papers[-1], "effect": "partially_addresses", "rationale": "TEST counterevidence retained.",
            }],
            "scores": {
                "novelty": {"value": 0.6, "kind": "heuristic", "algorithm": "motif-score-v1"},
                "feasibility": {"value": 0.8, "kind": "heuristic", "algorithm": "motif-score-v1"},
            },
        }]})
    gap_run = GapStore(project).detect(corpus["id"], motifs, test_only=True)
    gap = gap_run["candidate_gaps"][0]
    return {
        "project": project, "papers": papers, "problem": problem, "corpus": corpus,
        "motifs": motifs, "gap_run": gap_run, "gap": gap,
    }


def _experiment(identifier: str, hypothesis: str, repo: Path) -> dict:
    return {
        "id": identifier, "title": "TEST experiment", "status": "ANALYZED",
        "question": "Does the TEST fixture emit the metric?", "hypothesis": {"id": hypothesis},
        "evidence": {"papers": [], "repos": [], "observations": []},
        "baseline": {"repo": str(repo), "commit": None, "config": None},
        "change": {"summary": "TEST / MOCK"}, "scope": {"allowed_paths": [], "frozen_paths": []},
        "metrics": {"primary": "score", "secondary": [], "guardrails": {}},
        "budget": {"smoke": {}, "pilot": {}, "full": {}}, "stop_conditions": ["TEST done"],
        "compute": {"machine": "local", "gpu_count": 0},
        "approval": {"implementation": "approved", "pilot": "approved", "full": "approved"},
        "run": {"command": "python test.py", "required_tests": []}, "experiment_commit": None,
        "test_only": True, "created": "2026-09-05T00:00:00+00:00", "updated": "2026-09-05T00:00:00+00:00",
    }


def _claim_chain(project: ResearchProject, hypothesis: str) -> dict:
    experiment = allocate_id(research_home(), "EXP")
    write_yaml(project.root / "experiments/cards" / f"{experiment}.yaml", _experiment(experiment, hypothesis, project.repo))
    run_id = allocate_id(research_home(), "RUN")
    write_yaml(project.root / "runs" / run_id / "run.yaml", {
        "id": run_id, "experiment": experiment, "level": "smoke", "status": "succeeded",
        "started_at": "2026-09-05T00:00:00+00:00", "ended_at": "2026-09-05T00:00:01+00:00",
        "command": "python test.py", "git": {"repo": str(project.repo), "branch": "main", "commit": "TEST", "dirty": False, "diff_hash": None},
        "config": {"fixture": True}, "dataset": {"name": "TEST-DATASET"}, "environment": {"kind": "TEST"},
        "hardware": {"kind": "TEST"}, "artifacts": {}, "metrics": {"score": 0.75}, "exit_code": 0, "test_only": True,
    })
    finding = add_observation(project, "TEST Finding", "TEST result 0.75", [run_id], "high", "experimental_result")
    counter = add_observation(project, "TEST Counter Finding", "TEST limitation retained", [run_id], "medium", "experimental_result")
    metric_path = project.root / ".research" / f"metrics-{run_id}.json"
    metric_path.write_text(json.dumps({"metrics": {"score": 0.75}}), encoding="utf-8")
    artifact = ArtifactStore(project).add(metric_path, title="TEST metrics", artifact_type="metrics", derived_from=[run_id])["artifact"]
    request = project.root / ".research/claim.yaml"
    write_yaml(request, {
        "title": "TEST Claim", "statement": "TEST score is 0.75 under the registered conditions.",
        "scope": {"datasets": ["TEST-DATASET"], "platforms": ["TEST-SIM"], "seeds": [0], "conditions": ["TEST"]},
        "qualifiers": ["TEST / MOCK only"], "supporting_findings": [finding], "counter_findings": [counter],
        "metric_evidence": [{
            "run_id": run_id, "artifact_id": artifact["id"], "artifact_sha256": artifact["sha256"],
            "json_pointer": "/metrics/score", "metric_id": "score", "value": 0.75, "unit": "ratio",
        }], "status": "draft", "supersedes": None,
    })
    claim = ClaimStore(project).add_file(request)["claim"]["id"]
    return {"experiment": experiment, "run": run_id, "finding": finding, "counter": counter, "artifact": artifact, "claim": claim}


def test_corpus_extraction_gap_is_deterministic_and_human_gated(rf_env):
    fixture = _corpus_gap_fixture(rf_env)
    project = fixture["project"]
    corpora = CorpusStore(project)
    assert corpora.verify(fixture["corpus"]["id"])["valid"] is True
    assert corpora.extraction_status(fixture["corpus"]["id"])["complete_and_reviewed"] is True
    repeated = GapStore(project).detect(fixture["corpus"]["id"], fixture["motifs"], test_only=True)
    assert repeated["idempotent"] is True
    assert repeated["candidate_gaps"] == [fixture["gap"]]
    with pytest.raises(ResearchFlowError, match="human"):
        GapStore(project).review(fixture["gap"], decision="approve", reviewer="agent:test", rationale="TEST")
    with pytest.raises(ResearchFlowError, match="not currently approved"):
        add_hypothesis(project, "TEST H", "TEST statement", falsification="TEST false", gaps=[fixture["gap"]])
    GapStore(project).review(fixture["gap"], decision="approve", reviewer="human:pi", rationale="TEST approved for hypothesis formation.")
    hypothesis = add_hypothesis(project, "TEST H", "TEST statement", falsification="TEST falsification", gaps=[fixture["gap"]])
    metadata, _ = read_markdown_record(project.root / "memory/hypotheses" / f"{hypothesis}.md")
    assert metadata["based_on"]["gaps"] == [fixture["gap"]]
    assert metadata["provenance"]["gap_sources"][0]["reviewer"] == "human:pi"


def test_gap_detection_rolls_back_partial_candidate_and_run_files(rf_env, monkeypatch):
    fixture = _corpus_gap_fixture(rf_env)
    project = fixture["project"]
    gaps = GapStore(project)
    before_gaps = [item["id"] for item in gaps.list()]
    before_runs = sorted(path.parent.name for path in gaps.run_root.glob("CGAPRUN-*/manifest.yaml"))
    rules = read_yaml(fixture["motifs"])
    rules["version"] = "motif-rules-v2"
    write_yaml(fixture["motifs"], rules)
    real_atomic_text = corpus_gap_module.atomic_text

    def fail_candidate_log(path, content):
        if Path(path).name == "candidates.jsonl":
            raise OSError("TEST injected candidate-log failure")
        return real_atomic_text(path, content)

    monkeypatch.setattr(corpus_gap_module, "atomic_text", fail_candidate_log)
    with pytest.raises(OSError, match="candidate-log failure"):
        gaps.detect(fixture["corpus"]["id"], fixture["motifs"], test_only=True)
    assert [item["id"] for item in gaps.list()] == before_gaps
    assert sorted(path.parent.name for path in gaps.run_root.glob("CGAPRUN-*/manifest.yaml")) == before_runs


def test_complete_graph_review_counterevidence_and_export(rf_env):
    fixture = _corpus_gap_fixture(rf_env)
    project = fixture["project"]
    GapStore(project).review(fixture["gap"], decision="approve", reviewer="human:pi", rationale="TEST")
    hypothesis = add_hypothesis(project, "TEST H", "TEST statement", falsification="Metric is not 0.75.", gaps=[fixture["gap"]])
    chain = _claim_chain(project, hypothesis)
    graph = EvidenceGraphStore(project)
    graph.connect(fixture["problem"], "identifies", fixture["gap"])
    graph.connect(fixture["gap"], "motivates", hypothesis)
    graph.connect(hypothesis, "tested_by", chain["experiment"])
    graph.connect(chain["experiment"], "produces", chain["finding"])
    graph.connect(chain["finding"], "supports", chain["claim"])
    graph.connect(chain["counter"], "weakens", chain["claim"])
    graph.connect(chain["artifact"]["id"], "substantiates", chain["claim"])
    view = graph.claim_view(chain["claim"])
    assert view["structural_ready"] is True
    assert view["counterevidence_edges"][0]["from"] == chain["counter"]
    review = project.root / ".research/graph-review.yaml"
    write_yaml(review, {
        "target": chain["claim"], "target_fingerprint": view["claim_fingerprint"], "reviewer": "human:pi",
        "semantic_review": {
            "status": "pass", "rationale": "TEST scope and falsification inspected.",
            "experiment_falsifiable": "pass", "claim_within_findings": "pass",
        },
        "fidelity_review": {"status": "pending", "failures": [], "rationale": "TEST reproduction not checked."},
        "provenance": {"provider": "manual", "model": "none", "prompt_version": "v1", "input_fingerprint": graph.review_input_fingerprint(chain["claim"])},
    })
    imported = graph.import_review(chain["claim"], review)
    assert imported["overall_status"] == "pass"
    assert graph.claim_view(chain["claim"])["evidence_ready"] is True
    dot = project.root / ".research/evidence-graph/graph.dot"
    assert graph.export(dot)["changed"] is True
    assert "weakens" in dot.read_text(encoding="utf-8")


def test_claim_audit_isolated_from_unrelated_stale_edge(rf_env):
    fixture = _corpus_gap_fixture(rf_env)
    project = fixture["project"]
    hypothesis = add_hypothesis(project, "TEST H", "TEST", falsification="TEST false")
    valid = _claim_chain(project, hypothesis)
    graph = EvidenceGraphStore(project)
    graph.connect(hypothesis, "tested_by", valid["experiment"])
    graph.connect(valid["experiment"], "produces", valid["finding"])
    graph.connect(valid["finding"], "supports", valid["claim"])
    other_hypothesis = add_hypothesis(project, "OTHER H", "OTHER", falsification="OTHER false")
    other = _claim_chain(project, other_hypothesis)
    graph.connect(other_hypothesis, "tested_by", other["experiment"])
    graph.connect(other["experiment"], "produces", other["finding"])
    graph.connect(other["finding"], "supports", other["claim"])
    other_path = project.root / "memory/claims" / f"{other['claim']}.md"
    other_path.write_text(other_path.read_text(encoding="utf-8").replace("TEST Claim", "Changed OTHER Claim"), encoding="utf-8")
    assert graph.check()["valid"] is False
    isolated = graph.audit(valid["claim"], dry_run=True)
    assert isolated["deterministic_checks"]["status"] == "pass"


def test_migration_dry_run_snapshot_exact_edges_and_idempotency(rf_env, tmp_path):
    add_project("legacy", rf_env["repo"])
    project = ResearchProject.open("legacy")
    hypothesis = add_hypothesis(project, "TEST legacy H", "TEST", falsification="TEST false")
    chain = _claim_chain(project, hypothesis)
    graph = EvidenceGraphStore(project)
    graph.path.unlink()
    if graph.index_path.exists():
        graph.index_path.unlink()
    counters = (rf_env["home"] / ".id-counters.yaml").read_bytes()
    before = sorted(path.relative_to(project.root).as_posix() for path in project.root.rglob("*") if path.is_file())
    preview = migrate_corpus_gap_evidence_graph(project, dry_run=True, snapshot_dir=tmp_path / "snapshots")
    assert (rf_env["home"] / ".id-counters.yaml").read_bytes() == counters
    assert sorted(path.relative_to(project.root).as_posix() for path in project.root.rglob("*") if path.is_file()) == before
    assert not (tmp_path / "snapshots").exists()
    assert {item["relation"] for item in preview["edges"]} >= {"tested_by", "produces", "supports", "substantiates"}
    applied = migrate_corpus_gap_evidence_graph(
        project, plan_fingerprint=preview["plan_fingerprint"], snapshot_dir=tmp_path / "snapshots",
    )
    assert verify_snapshot(Path(applied["snapshot"]), expected_project_id="legacy")["valid"] is True
    assert EvidenceGraphStore(project).check()["valid"] is True
    repeated = migrate_corpus_gap_evidence_graph(
        project, plan_fingerprint=preview["plan_fingerprint"], snapshot_dir=tmp_path / "snapshots",
    )
    assert repeated["idempotent"] is True and repeated["changed"] is False

    post = create_snapshot(project, tmp_path / "post-snapshots")
    restored = tmp_path / "restored-legacy"
    restore_snapshot(project, Path(post["snapshot"]), target=restored)
    source_index = json.loads(EvidenceGraphStore(project).index_path.read_text(encoding="utf-8"))
    restored_index = json.loads((restored / ".research/evidence-graph/index.json").read_text(encoding="utf-8"))
    assert source_index["graph_fingerprint"] == restored_index["graph_fingerprint"]


def test_migration_aborts_before_authority_writes_when_snapshot_verification_fails(rf_env, tmp_path, monkeypatch):
    add_project("legacy", rf_env["repo"])
    project = ResearchProject.open("legacy")
    hypothesis = add_hypothesis(project, "TEST legacy H", "TEST", falsification="TEST false")
    _claim_chain(project, hypothesis)
    graph = EvidenceGraphStore(project)
    graph.path.unlink()
    graph.index_path.unlink(missing_ok=True)
    preview = migrate_corpus_gap_evidence_graph(project, dry_run=True, snapshot_dir=tmp_path / "snapshots")
    monkeypatch.setattr(migration_module, "verify_snapshot", lambda *args, **kwargs: {
        "valid": False, "issues": ["TEST injected verification failure"],
    })
    with pytest.raises(ResearchFlowError, match="snapshot verification failed"):
        migrate_corpus_gap_evidence_graph(
            project, plan_fingerprint=preview["plan_fingerprint"], snapshot_dir=tmp_path / "snapshots",
        )
    assert not graph.path.exists()
    assert not graph.index_path.exists()
    assert not (project.root / ".research/migrations/corpus-gap-evidence-graph-v1.yaml").exists()


def test_migration_rolls_back_authority_files_after_injected_failure(rf_env, tmp_path, monkeypatch):
    add_project("legacy", rf_env["repo"])
    project = ResearchProject.open("legacy")
    hypothesis = add_hypothesis(project, "TEST legacy H", "TEST", falsification="TEST false")
    _claim_chain(project, hypothesis)
    graph = EvidenceGraphStore(project)
    graph.path.unlink()
    graph.index_path.unlink(missing_ok=True)
    knowledge_before = (project.root / "KNOWLEDGE.md").read_bytes()
    preview = migrate_corpus_gap_evidence_graph(project, dry_run=True, snapshot_dir=tmp_path / "snapshots")

    def fail_rebuild(*args, **kwargs):
        raise ResearchFlowError("TEST injected rebuild failure")

    monkeypatch.setattr(EvidenceGraphStore, "rebuild", fail_rebuild)
    with pytest.raises(ResearchFlowError, match="injected rebuild failure"):
        migrate_corpus_gap_evidence_graph(
            project, plan_fingerprint=preview["plan_fingerprint"], snapshot_dir=tmp_path / "snapshots",
        )
    assert not graph.path.exists()
    assert not graph.index_path.exists()
    assert (project.root / "KNOWLEDGE.md").read_bytes() == knowledge_before
    assert not (project.root / ".research/migrations/corpus-gap-evidence-graph-v1.yaml").exists()
    assert not (project.root / ".research/migrations/corpus-gap-evidence-graph-v1-report.json").exists()
    failure = read_yaml(project.root / ".research/migrations/corpus-gap-evidence-graph-v1-failure.yaml")
    assert "TEST injected rebuild failure" in failure["error"]
    assert verify_snapshot(Path(failure["snapshot"]), expected_project_id="legacy")["valid"] is True
