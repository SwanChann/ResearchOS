from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .errors import ResearchFlowError
from .evidence_graph import EvidenceGraphStore, RecordResolver
from .io import atomic_text, exclusive_lock, read_markdown_record, read_yaml, utc_now, write_yaml
from .schema import validate_record
from .snapshot import create_snapshot, default_snapshot_dir, verify_snapshot


MIGRATION_NAME = "corpus-gap-evidence-graph-v1"
MARKER = Path(".research/migrations/corpus-gap-evidence-graph-v1.yaml")
REPORT = Path(".research/migrations/corpus-gap-evidence-graph-v1-report.json")


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _source_files(project) -> list[Path]:
    patterns = (
        "memory/hypotheses/HYP-*.md", "memory/observations/OBS-*.md",
        "memory/claims/CLAIM-*.md", "experiments/cards/EXP-*.yaml",
        "runs/RUN-*/run.yaml", ".research/artifacts.yaml",
    )
    return sorted(
        {path for pattern in patterns for path in project.root.glob(pattern) if path.is_file()},
        key=lambda path: path.relative_to(project.root).as_posix(),
    )


def _input_fingerprint(project) -> tuple[str, list[dict[str, Any]]]:
    entries = []
    for path in _source_files(project):
        payload = path.read_bytes()
        entries.append({
            "path": path.relative_to(project.root).as_posix(),
            "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
        })
    return _hash(entries), entries


def _plan(project) -> dict[str, Any]:
    resolver = RecordResolver(project)
    edges: set[tuple[str, str, str]] = set()
    unmapped: list[dict[str, Any]] = []
    hypotheses = {path.stem for path in (project.root / "memory/hypotheses").glob("HYP-*.md")}
    experiments: dict[str, dict[str, Any]] = {}
    for path in sorted((project.root / "experiments/cards").glob("EXP-*.yaml")):
        card = read_yaml(path)
        experiments[card["id"]] = card
        hypothesis = card.get("hypothesis", {}).get("id")
        if hypothesis in hypotheses:
            edges.add((hypothesis, "tested_by", card["id"]))
        else:
            unmapped.append({"record": card.get("id", path.stem), "relation": "tested_by", "reason": "missing exact Hypothesis ID"})

    runs: dict[str, dict[str, Any]] = {}
    for path in sorted((project.root / "runs").glob("RUN-*/run.yaml")):
        run = read_yaml(path)
        runs[run["id"]] = run

    observations: dict[str, dict[str, Any]] = {}
    for path in sorted((project.root / "memory/observations").glob("OBS-*.md")):
        observation, _ = read_markdown_record(path)
        observations[observation["id"]] = observation
        if observation.get("type") != "experimental_result":
            continue
        linked = False
        for ref in observation.get("evidence", {}).get("refs", []):
            if ref.startswith("RUN-") and ref in runs:
                run = runs[ref]
                experiment = run.get("experiment")
                if run.get("status") == "succeeded" and experiment in experiments:
                    edges.add((experiment, "produces", observation["id"]))
                    linked = True
            elif ref.startswith("ARTIFACT-") and resolver.exists(ref):
                edges.add((ref, "substantiates", observation["id"]))
        if not linked:
            unmapped.append({"record": observation["id"], "relation": "produces", "reason": "no succeeded RUN with an exact Experiment reference"})

    for path in sorted((project.root / "memory/claims").glob("CLAIM-*.md")):
        claim, _ = read_markdown_record(path)
        claim_id = claim["id"]
        for finding in claim.get("supporting_findings", []):
            if finding in observations:
                edges.add((finding, "supports", claim_id))
            else:
                unmapped.append({"record": claim_id, "relation": "supports", "reason": f"missing exact Finding {finding}"})
        for finding in claim.get("counter_findings", []):
            if finding in observations:
                edges.add((finding, "weakens", claim_id))
            else:
                unmapped.append({"record": claim_id, "relation": "weakens", "reason": f"missing exact Finding {finding}"})
        for metric in claim.get("metric_evidence", []):
            artifact = metric.get("artifact_id")
            if artifact and resolver.exists(artifact):
                edges.add((artifact, "substantiates", claim_id))
            else:
                unmapped.append({"record": claim_id, "relation": "substantiates", "reason": f"missing exact Artifact {artifact}"})

    edge_values = [
        {"from": source, "relation": relation, "to": target}
        for source, relation, target in sorted(edges)
    ]
    input_fingerprint, inputs = _input_fingerprint(project)
    stable = {
        "migration": MIGRATION_NAME, "project_id": project.data["id"],
        "schema_version": 1, "input_fingerprint": input_fingerprint,
        "inputs": inputs, "edges": edge_values, "unmapped": unmapped,
        "directories": [
            "memory/problems", "memory/gaps", "memory/claims", "evidence/corpora",
            "evidence/corpus-extractions", ".research/evidence-graph/audits", ".research/corpus-gap/runs",
        ],
        "will_not_create": ["PROB", "GAP", "CLAIM"],
    }
    return {**stable, "plan_fingerprint": _hash(stable)}


def _restore_files(originals: dict[Path, bytes | None]) -> None:
    for path, payload in originals.items():
        if payload is None:
            path.unlink(missing_ok=True)
        else:
            atomic_text(path, payload.decode("utf-8"))


def migrate_corpus_gap_evidence_graph(
    project,
    *,
    dry_run: bool = False,
    plan_fingerprint: str | None = None,
    snapshot_dir: Path | None = None,
) -> dict[str, Any]:
    plan = _plan(project)
    snapshot_root = (snapshot_dir or default_snapshot_dir(project)).expanduser().resolve()
    rollback_template = (
        f"rf --project {project.data['id']} snapshot restore <SNAPSHOT> "
        f"--target <NEW-RESTORE-DIRECTORY>"
    )
    preview = {
        **plan, "dry_run": dry_run, "snapshot_directory": str(snapshot_root),
        "expected_snapshot_pattern": f"{project.data['id']}-*.rfsnapshot",
        "rollback": rollback_template,
    }
    if dry_run:
        return preview
    if not plan_fingerprint:
        raise ResearchFlowError("Non-dry-run migration requires --plan-fingerprint from the current dry-run output.")
    if plan_fingerprint != plan["plan_fingerprint"]:
        raise ResearchFlowError("Migration plan fingerprint changed; rerun --dry-run and review the new plan.")

    marker_path = project.root / MARKER
    if marker_path.exists():
        marker = read_yaml(marker_path)
        validate_record("evidence_graph_migration", marker)
        if marker["input_fingerprint"] == plan["input_fingerprint"] and marker["plan_fingerprint"] == plan_fingerprint:
            return {**marker, "changed": False, "idempotent": True, "dry_run": False}
        raise ResearchFlowError("A migration marker exists for different inputs; run a new dry-run before changing the project.")

    graph = EvidenceGraphStore(project)
    protected = {
        graph.path: graph.path.read_bytes() if graph.path.exists() else None,
        graph.index_path: graph.index_path.read_bytes() if graph.index_path.exists() else None,
        marker_path: None,
        project.root / REPORT: None,
        project.root / "KNOWLEDGE.md": (project.root / "KNOWLEDGE.md").read_bytes(),
    }
    migration_directories = [project.root / item for item in plan["directories"]]
    missing_directories = [path for path in migration_directories if not path.exists()]
    with exclusive_lock(project.root / ".locks/corpus-gap-evidence-graph-migration.lock"):
        current = _plan(project)
        if current["plan_fingerprint"] != plan_fingerprint:
            raise ResearchFlowError("Migration inputs changed after approval; rerun --dry-run.")
        snapshot = create_snapshot(project, snapshot_root)
        verified = verify_snapshot(Path(snapshot["snapshot"]), expected_project_id=project.data["id"])
        if not verified["valid"]:
            raise ResearchFlowError("Migration snapshot verification failed: " + "; ".join(verified["issues"]))
        rollback = (
            f"rf --project {project.data['id']} snapshot restore {snapshot['snapshot']} "
            f"--target <NEW-RESTORE-DIRECTORY>"
        )
        try:
            for directory in migration_directories:
                directory.mkdir(parents=True, exist_ok=True)
            graph.initialize()
            connected = []
            for edge in plan["edges"]:
                result = graph.connect(edge["from"], edge["relation"], edge["to"])
                connected.append(result["edge"]["id"])
            rebuilt = graph.rebuild()
            checked = graph.check()
            if not checked["valid"]:
                raise ResearchFlowError("Post-migration graph check failed: " + "; ".join(checked["issues"]))
            from .knowledge import KnowledgeStore
            knowledge = KnowledgeStore(project)
            knowledge.rebuild()
            if not knowledge.check()["valid"]:
                raise ResearchFlowError("Post-migration Knowledge check failed.")
            report = {
                "migration": MIGRATION_NAME, "project_id": project.data["id"],
                "input_fingerprint": plan["input_fingerprint"], "plan_fingerprint": plan_fingerprint,
                "connected_edge_ids": connected, "unmapped": plan["unmapped"],
                "graph_fingerprint": rebuilt["graph_fingerprint"],
                "meaning": "Exact-reference software migration only; no Problem, Gap, Claim, or scientific conclusion was inferred.",
            }
            atomic_text(project.root / REPORT, json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            marker = {
                "schema_version": 1, "migration": MIGRATION_NAME, "project_id": project.data["id"],
                "input_fingerprint": plan["input_fingerprint"], "plan_fingerprint": plan_fingerprint,
                "edges": plan["edges"], "unmapped": plan["unmapped"],
                "snapshot": snapshot["snapshot"], "rollback": rollback, "created_at": utc_now(),
            }
            validate_record("evidence_graph_migration", marker)
            write_yaml(marker_path, marker)
            # Status is intentionally evaluated last as a compatibility assertion.
            project.status()
            return {**marker, "changed": True, "idempotent": False, "dry_run": False}
        except Exception as exc:
            _restore_files(protected)
            for directory in reversed(missing_directories):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            failure = project.root / ".research/migrations/corpus-gap-evidence-graph-v1-failure.yaml"
            write_yaml(failure, {
                "migration": MIGRATION_NAME, "error": str(exc), "snapshot": snapshot["snapshot"],
                "rollback": rollback, "failed_at": utc_now(),
            })
            raise
