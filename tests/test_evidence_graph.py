import json
import hashlib
import shutil
from pathlib import Path

import pytest

from researchflow.artifact import ArtifactStore
from researchflow.config import research_home
from researchflow.errors import ResearchFlowError
from researchflow.evidence_graph import ClaimStore, EvidenceGraphStore, ProblemStore
from researchflow.ids import allocate_id, validate_id
from researchflow.io import read_markdown_record, read_yaml, write_yaml
from researchflow.knowledge import KnowledgeStore
from researchflow.project import ResearchProject, add_project
from researchflow.records import add_hypothesis, add_observation, broken_references


def _write_problem_request(path: Path) -> None:
    write_yaml(path, {
        "title": "TEST navigation reliability",
        "objective": "Test the EvidenceGraph contract.",
        "scope": "TEST / MOCK records only.",
        "constraints": ["No external execution"],
        "application_context": "TEST inspection",
        "status": "active",
        "supersedes": None,
        "body": "TEST / MOCK Problem. It does not assert that a research gap exists.",
    })


def _experiment(identifier: str, hypothesis: str, repo: Path) -> dict:
    return {
        "id": identifier,
        "title": "TEST experiment",
        "status": "ANALYZED",
        "question": "Does the TEST fixture emit the registered metric?",
        "hypothesis": {"id": hypothesis},
        "evidence": {"papers": [], "repos": [], "observations": []},
        "baseline": {"repo": str(repo), "commit": None, "config": None},
        "change": {"summary": "TEST / MOCK only"},
        "scope": {"allowed_paths": [], "frozen_paths": []},
        "metrics": {"primary": "score", "secondary": [], "guardrails": {}},
        "budget": {"smoke": {}, "pilot": {}, "full": {}},
        "stop_conditions": ["TEST complete"],
        "compute": {"machine": "local", "gpu_count": 0},
        "approval": {"implementation": "approved", "pilot": "approved", "full": "approved"},
        "run": {"command": "python test_fixture.py", "required_tests": []},
        "experiment_commit": None,
        "test_only": True,
        "created": "2026-09-05T00:00:00+00:00",
        "updated": "2026-09-05T00:00:00+00:00",
    }


def _run(identifier: str, experiment: str, repo: Path) -> dict:
    return {
        "id": identifier,
        "experiment": experiment,
        "level": "smoke",
        "status": "succeeded",
        "started_at": "2026-09-05T00:00:00+00:00",
        "ended_at": "2026-09-05T00:00:01+00:00",
        "command": "python test_fixture.py",
        "git": {"repo": str(repo), "branch": "main", "commit": "TEST", "dirty": False, "diff_hash": None},
        "config": {"fixture": True},
        "dataset": {"name": "TEST-DATASET"},
        "environment": {"kind": "TEST"},
        "hardware": {"kind": "TEST / MOCK"},
        "artifacts": {},
        "metrics": {"score": 0.75},
        "exit_code": 0,
        "test_only": True,
    }


def _claim_request(path: Path, finding: str, run_id: str, artifact: dict, *, value=0.75) -> None:
    write_yaml(path, {
        "title": "TEST bounded score claim",
        "statement": "The TEST fixture reports score 0.75 under the registered conditions.",
        "scope": {
            "datasets": ["TEST-DATASET"],
            "platforms": ["TEST-SIM"],
            "seeds": [0],
            "conditions": ["TEST / MOCK only"],
        },
        "qualifiers": ["Not scientific evidence"],
        "supporting_findings": [finding],
        "counter_findings": [],
        "metric_evidence": [{
            "run_id": run_id,
            "artifact_id": artifact["id"],
            "artifact_sha256": artifact["sha256"],
            "json_pointer": "/metrics/score",
            "metric_id": "score",
            "value": value,
            "unit": "ratio",
        }],
        "status": "draft",
        "supersedes": None,
        "body": "TEST / MOCK Claim; semantic review and scientific establishment are pending.",
    })


def _fixture(rf_env) -> dict:
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    observation = add_observation(project, "TEST premise", "TEST / MOCK premise")
    hypothesis = add_hypothesis(
        project, "TEST hypothesis", "The fixture emits score 0.75.", [observation],
        falsification="The exact registered value is not 0.75.",
    )
    experiment = allocate_id(research_home(), "EXP")
    write_yaml(project.root / "experiments" / "cards" / f"{experiment}.yaml", _experiment(experiment, hypothesis, project.repo))
    run_id = allocate_id(research_home(), "RUN")
    write_yaml(project.root / "runs" / run_id / "run.yaml", _run(run_id, experiment, project.repo))
    finding = add_observation(
        project, "TEST Finding", "The registered TEST metric is 0.75.", [run_id],
        confidence="high", observation_type="experimental_result",
    )
    metric_path = project.root / ".research" / "test-metrics.json"
    metric_path.write_text(json.dumps({"metrics": {"score": 0.75}}) + "\n", encoding="utf-8")
    artifact = ArtifactStore(project).add(
        metric_path, title="TEST metrics", artifact_type="metrics", derived_from=[run_id]
    )["artifact"]
    request = project.root / ".research" / "claim-request.yaml"
    _claim_request(request, finding, run_id, artifact)
    claim = ClaimStore(project).add_file(request)["claim"]["id"]
    return {
        "project": project, "hypothesis": hypothesis, "experiment": experiment,
        "run": run_id, "finding": finding, "artifact": artifact, "claim": claim,
        "claim_request": request,
    }


def test_phase_a_ids_and_new_project_layout(rf_env):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    for relative in (
        "memory/problems", "memory/gaps", "memory/claims", "evidence/corpora",
        "evidence/corpus-extractions", ".research/evidence-graph/audits",
    ):
        assert (project.root / relative).is_dir()
    assert (project.root / ".research/evidence-graph/edges.yaml").is_file()
    assert validate_id(allocate_id(research_home(), "PROB"), "PROB")
    assert validate_id(allocate_id(research_home(), "CLAIM"), "CLAIM")
    assert validate_id(allocate_id(research_home(), "EGAUDIT"), "EGAUDIT")


def test_problem_preflight_dry_run_and_idempotent_import(rf_env):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    request = project.root / ".research" / "problem-request.yaml"
    _write_problem_request(request)
    store = ProblemStore(project)
    assert store.preflight(request)["valid"] is True
    before = (rf_env["home"] / ".id-counters.yaml").read_text(encoding="utf-8") if (rf_env["home"] / ".id-counters.yaml").exists() else ""
    assert store.add_file(request, dry_run=True)["dry_run"] is True
    after = (rf_env["home"] / ".id-counters.yaml").read_text(encoding="utf-8") if (rf_env["home"] / ".id-counters.yaml").exists() else ""
    assert before == after
    created = store.add_file(request)
    assert created["problem"]["id"] == "PROB-0001"
    assert store.add_file(request)["idempotent"] is True
    assert read_markdown_record(project.root / "memory/problems/PROB-0001.md")[0]["status"] == "active"


def test_claim_requires_exact_registered_metric_and_finding(rf_env):
    fixture = _fixture(rf_env)
    store = ClaimStore(fixture["project"])
    assert store.preflight(fixture["claim_request"])["idempotent_existing_id"] == fixture["claim"]
    bad = fixture["project"].root / ".research" / "bad-claim.yaml"
    _claim_request(bad, fixture["finding"], fixture["run"], fixture["artifact"], value=0.8)
    with pytest.raises(ResearchFlowError, match="value mismatch"):
        store.preflight(bad)
    assert broken_references(fixture["project"]) == []


def test_claim_metric_identity_alias_and_predeclared_tolerance(rf_env):
    fixture = _fixture(rf_env)
    store = ClaimStore(fixture["project"])

    mismatched = read_yaml(fixture["claim_request"])
    mismatched["metric_evidence"][0]["metric_id"] = "canonical_score"
    mismatch_path = fixture["project"].root / ".research" / "mismatched-metric.yaml"
    write_yaml(mismatch_path, mismatched)
    with pytest.raises(ResearchFlowError, match="alias map is required"):
        store.preflight(mismatch_path)

    alias_path = fixture["project"].root / ".research" / "metric-alias-v1.yaml"
    write_yaml(alias_path, {
        "schema_version": 1, "version": "v1", "aliases": {"canonical_score": ["score"]},
    })
    mismatched["metric_evidence"][0]["alias_map"] = {
        "path": ".research/metric-alias-v1.yaml", "version": "v1",
        "sha256": hashlib.sha256(alias_path.read_bytes()).hexdigest(), "alias": "score",
    }
    write_yaml(mismatch_path, mismatched)
    assert store.preflight(mismatch_path)["valid"] is True

    tolerant = read_yaml(fixture["claim_request"])
    tolerant["metric_evidence"][0]["value"] = 0.7505
    tolerant["metric_evidence"][0]["tolerance"] = 0.001
    tolerance_path = fixture["project"].root / ".research" / "tolerant-metric.yaml"
    write_yaml(tolerance_path, tolerant)
    with pytest.raises(ResearchFlowError, match="was not predeclared"):
        store.preflight(tolerance_path)
    experiment_path = fixture["project"].root / "experiments" / "cards" / f"{fixture['experiment']}.yaml"
    experiment = read_yaml(experiment_path)
    experiment["metrics"]["guardrails"]["metric_tolerances"] = {"score": 0.001}
    write_yaml(experiment_path, experiment)
    assert store.preflight(tolerance_path)["valid"] is True


def test_claim_supersede_is_explicit_and_preserves_both_records(rf_env):
    fixture = _fixture(rf_env)
    store = ClaimStore(fixture["project"])
    replacement = read_yaml(fixture["claim_request"])
    replacement["title"] = "TEST bounded replacement claim"
    replacement["supersedes"] = fixture["claim"]
    replacement_path = fixture["project"].root / ".research" / "replacement-claim.yaml"
    write_yaml(replacement_path, replacement)
    assert store.supersede_file(fixture["claim"], replacement_path, dry_run=True)["dry_run"] is True
    assert store.show(fixture["claim"])["metadata"]["status"] == "draft"
    result = store.supersede_file(fixture["claim"], replacement_path)
    replacement_id = result["claim"]["id"]
    assert store.show(fixture["claim"])["metadata"]["status"] == "superseded"
    assert store.show(replacement_id)["metadata"]["supersedes"] == fixture["claim"]


def test_graph_chain_is_structurally_ready_but_semantics_fail_closed(rf_env):
    fixture = _fixture(rf_env)
    graph = EvidenceGraphStore(fixture["project"])
    graph.connect(fixture["hypothesis"], "tested_by", fixture["experiment"])
    graph.connect(fixture["experiment"], "produces", fixture["finding"])
    graph.connect(fixture["finding"], "supports", fixture["claim"])
    graph.connect(fixture["artifact"]["id"], "substantiates", fixture["claim"])
    view = graph.claim_view(fixture["claim"])
    assert view["chains"] == [[fixture["hypothesis"], fixture["experiment"], fixture["finding"], fixture["claim"]]]
    assert view["structural_ready"] is True
    assert view["semantic_review"] == "pending"
    assert view["evidence_ready"] is False
    assert graph.check()["valid"] is True
    assert graph.check()["ready"] is False

    counters = (rf_env["home"] / ".id-counters.yaml").read_text(encoding="utf-8")
    preview = graph.audit(fixture["claim"], dry_run=True)
    assert preview["id"] is None and preview["written"] is False
    assert (rf_env["home"] / ".id-counters.yaml").read_text(encoding="utf-8") == counters
    assert not list(graph.audit_folder.glob("EGAUDIT-*.yaml"))
    audit = graph.audit(fixture["claim"])
    assert audit["deterministic_checks"]["status"] == "pass"
    assert audit["semantic_review"]["status"] == "pending"
    assert audit["overall_status"] == "pending"
    assert audit["written"] is True
    assert graph.claim_view(fixture["claim"])["evidence_ready"] is False
    status = fixture["project"].status()["evidence_graph"]
    assert status["claims"] == 1
    assert status["pending_or_blocked_claims"] == [fixture["claim"]]
    knowledge = KnowledgeStore(fixture["project"])
    knowledge.rebuild()
    rendered = knowledge.path.read_text(encoding="utf-8")
    assert fixture["claim"] in rendered
    assert "scientific-claim-unestablished" in rendered
    from researchflow.doctor import run_doctor
    doctor_graph = next(item for item in run_doctor("toy") if item.name == "project toy evidence graph")
    assert doctor_graph.status == "WARN"


def test_graph_dry_run_idempotency_rebuild_and_staleness(rf_env):
    fixture = _fixture(rf_env)
    graph = EvidenceGraphStore(fixture["project"])
    before = read_yaml(graph.path)
    preview = graph.connect(fixture["hypothesis"], "tested_by", fixture["experiment"], dry_run=True)
    assert preview["dry_run"] is True
    assert read_yaml(graph.path) == before
    first = graph.connect(fixture["hypothesis"], "tested_by", fixture["experiment"])
    assert graph.connect(fixture["hypothesis"], "tested_by", fixture["experiment"])["idempotent"] is True
    rebuilt = graph.rebuild()
    assert rebuilt["changed"] is True
    assert graph.rebuild()["changed"] is False
    assert json.loads(graph.index_path.read_text(encoding="utf-8"))["graph_fingerprint"] == rebuilt["graph_fingerprint"]

    claim_path = fixture["project"].root / "memory/claims" / f"{fixture['claim']}.md"
    claim_path.write_text(claim_path.read_text(encoding="utf-8").replace("semantic review", "human semantic review"), encoding="utf-8")
    graph.connect(fixture["finding"], "supports", fixture["claim"])
    ledger = read_yaml(graph.path)
    assert first["edge"]["id"] in {item["id"] for item in ledger["edges"]}
    claim_path.write_text(claim_path.read_text(encoding="utf-8").replace("human semantic review", "changed semantic review"), encoding="utf-8")
    checked = graph.check()
    assert checked["valid"] is False
    assert any("stale" in issue for issue in checked["issues"])


def test_graph_rejects_wrong_endpoint_and_inconsistent_relation(rf_env):
    fixture = _fixture(rf_env)
    graph = EvidenceGraphStore(fixture["project"])
    with pytest.raises(ResearchFlowError, match="Invalid EvidenceGraph endpoints"):
        graph.connect(fixture["experiment"], "supports", fixture["claim"])
    with pytest.raises(ResearchFlowError, match="Finding has no RUN"):
        graph.connect(fixture["experiment"], "produces", add_observation(
            fixture["project"], "TEST unrelated", "No run reference", observation_type="experimental_result"
        ))


def test_reconnecting_changed_records_supersedes_old_edge(rf_env):
    fixture = _fixture(rf_env)
    graph = EvidenceGraphStore(fixture["project"])
    graph.connect(fixture["hypothesis"], "tested_by", fixture["experiment"])
    graph.connect(fixture["experiment"], "produces", fixture["finding"])
    old = graph.connect(fixture["finding"], "supports", fixture["claim"])["edge"]
    claim_path = fixture["project"].root / "memory/claims" / f"{fixture['claim']}.md"
    claim_path.write_text(
        claim_path.read_text(encoding="utf-8").replace("semantic review", "current semantic review"),
        encoding="utf-8",
    )
    replacement = graph.connect(fixture["finding"], "supports", fixture["claim"])
    assert replacement["superseded_edge"] == old["id"]
    ledger = read_yaml(graph.path)
    by_id = {item["id"]: item for item in ledger["edges"]}
    assert by_id[old["id"]]["status"] == "superseded"
    assert by_id[replacement["edge"]["id"]]["supersedes"] == old["id"]
    assert graph.check()["valid"] is True


def test_graph_rechecks_artifact_hash_and_metric_after_claim_import(rf_env):
    fixture = _fixture(rf_env)
    graph = EvidenceGraphStore(fixture["project"])
    graph.connect(fixture["hypothesis"], "tested_by", fixture["experiment"])
    graph.connect(fixture["experiment"], "produces", fixture["finding"])
    graph.connect(fixture["finding"], "supports", fixture["claim"])
    assert graph.check()["valid"] is True
    metric_path = fixture["project"].root / fixture["artifact"]["path"]
    metric_path.write_text(json.dumps({"metrics": {"score": 0.9}}) + "\n", encoding="utf-8")
    checked = graph.check()
    assert checked["valid"] is False
    assert any("Artifact hash" in issue for issue in checked["issues"])
    audit = graph.audit(fixture["claim"], dry_run=True)
    assert audit["deterministic_checks"]["status"] == "fail"
    assert audit["overall_status"] == "fail"


def test_problem_claim_graph_cli_and_read_only_projections(rf_env, capsys):
    assert __import__("researchflow.cli", fromlist=["main"]).main([
        "project", "add", "toy", "--repo", str(rf_env["repo"])
    ]) == 0
    project = ResearchProject.open("toy")
    problem_request = project.root / ".research" / "problem-request.yaml"
    _write_problem_request(problem_request)
    from researchflow.cli import main
    assert main(["scaffold", "problem", "--output", str(project.root / ".research" / "problem-draft.yaml")]) == 0
    assert main(["preflight", "problem", str(problem_request)]) == 0
    assert main(["evidence", "problem", "add", str(problem_request), "--dry-run"]) == 0
    assert not list((project.root / "memory/problems").glob("PROB-*.md"))
    assert main(["evidence", "problem", "add", str(problem_request)]) == 0
    assert main(["evidence", "problem", "show", "PROB-0001"]) == 0
    assert main(["evidence", "graph", "check"]) == 0
    assert main(["evidence", "graph", "check", "--strict"]) == 1
    status = project.status()
    assert status["evidence_graph"]["initialized"] is True
    KnowledgeStore(project).rebuild()
    assert "PROB-0001" in project.root.joinpath("KNOWLEDGE.md").read_text(encoding="utf-8")
    assert "scientific" not in capsys.readouterr().err.lower()


def test_legacy_project_status_and_doctor_do_not_initialize_graph(rf_env):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    graph_folder = project.root / ".research/evidence-graph"
    shutil.rmtree(graph_folder)
    status = project.status()
    assert status["evidence_graph"]["initialized"] is False
    assert not graph_folder.exists()
    from researchflow.doctor import run_doctor
    checks = run_doctor("toy")
    graph_check = next(item for item in checks if item.name == "project toy evidence graph")
    assert graph_check.status == "WARN"
    assert "no migration was performed" in graph_check.detail
    assert not graph_folder.exists()
