from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .artifact import ArtifactStore
from .config import research_home
from .errors import ResearchFlowError
from .ids import allocate_id
from .io import atomic_text, exclusive_lock, markdown_record, read_markdown_record, read_yaml, utc_now, write_yaml
from .schema import validate_record


GRAPH_RELATIVE_PATH = Path(".research/evidence-graph/edges.yaml")
INDEX_RELATIVE_PATH = Path(".research/evidence-graph/index.json")
AUDIT_RELATIVE_PATH = Path(".research/evidence-graph/audits")
LOCK_RELATIVE_PATH = Path(".locks/evidence-graph-write.lock")

ALLOWED_RELATIONS: dict[str, tuple[set[str], set[str]]] = {
    "identifies": ({"PROB"}, {"GAP"}),
    "motivates": ({"GAP"}, {"HYP"}),
    "tested_by": ({"HYP"}, {"EXP"}),
    "produces": ({"EXP"}, {"OBS"}),
    "supports": ({"OBS"}, {"CLAIM"}),
    "weakens": ({"OBS"}, {"CLAIM"}),
    "contradicts": ({"OBS"}, {"CLAIM"}),
    "supports_gap": ({"PAPER"}, {"GAP"}),
    "weakens_gap": ({"PAPER"}, {"GAP"}),
    "substantiates": ({"ARTIFACT"}, {"OBS", "CLAIM"}),
}
DEPENDENCY_RELATIONS = {"identifies", "motivates", "tested_by", "produces"}


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _metric_values_equal(actual: Any, expected: Any, tolerance: float = 0.0) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return abs(actual - expected) <= tolerance
    return type(actual) is type(expected) and actual == expected


def _prefix(identifier: str) -> str:
    return identifier.split("-", 1)[0]


def _json_pointer(document: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise ResearchFlowError(f"JSON Pointer must start with '/': {pointer}")
    current = document
    for raw in pointer[1:].split("/"):
        if re.search(r"~(?![01])", raw):
            raise ResearchFlowError(f"JSON Pointer contains an invalid escape: {pointer}")
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")) or int(token) >= len(current):
                raise ResearchFlowError(f"JSON Pointer does not resolve: {pointer}")
            current = current[int(token)]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise ResearchFlowError(f"JSON Pointer does not resolve: {pointer}")
    return current


def _json_pointer_tokens(pointer: str) -> list[str]:
    if not pointer.startswith("/"):
        raise ResearchFlowError(f"JSON Pointer must start with '/': {pointer}")
    tokens = []
    for raw in pointer[1:].split("/"):
        if re.search(r"~(?![01])", raw):
            raise ResearchFlowError(f"JSON Pointer contains an invalid escape: {pointer}")
        tokens.append(raw.replace("~1", "/").replace("~0", "~"))
    return tokens


class RecordResolver:
    """Resolve authoritative project records without copying their content into the graph."""

    MARKDOWN = {
        "OBS": ("memory/observations", "observation"),
        "HYP": ("memory/hypotheses", "hypothesis"),
        "DEC": ("memory/decisions", "decision"),
        "PAPER": ("evidence/papers/analysis", "paper"),
        "PROB": ("memory/problems", "problem"),
        "CLAIM": ("memory/claims", "claim"),
        "GAP": ("memory/gaps", "gap"),
    }
    YAML = {
        "EXP": ("experiments/cards", "experiment"),
        "REPO": ("evidence/repos/manifests", "repository_evidence"),
        "CORPUS": ("evidence/corpora", "corpus"),
    }

    def __init__(self, project):
        self.project = project

    def resolve(self, identifier: str) -> dict[str, Any]:
        kind = _prefix(identifier)
        if kind == "RUN":
            path = self.project.root / "runs" / identifier / "run.yaml"
            if not path.is_file():
                raise ResearchFlowError(f"Record not found: {identifier}")
            data = read_yaml(path)
            validate_record("run", data)
            return self._resolved(identifier, kind, path, data)
        if kind == "ARTIFACT":
            data = ArtifactStore(self.project).show(identifier)
            return self._resolved(identifier, kind, ArtifactStore(self.project)._registry_file(data["path"]), data)
        if kind == "EGAUDIT":
            path = self.project.root / AUDIT_RELATIVE_PATH / f"{identifier}.yaml"
            if not path.is_file():
                raise ResearchFlowError(f"Record not found: {identifier}")
            data = read_yaml(path)
            validate_record("evidence_graph_audit", data)
            return self._resolved(identifier, kind, path, data)
        if kind == "CGAPRUN":
            path = self.project.root / ".research" / "corpus-gap" / "runs" / identifier / "manifest.yaml"
            if not path.is_file():
                raise ResearchFlowError(f"Record not found: {identifier}")
            data = read_yaml(path)
            validate_record("corpus_gap_run", data)
            return self._resolved(identifier, kind, path, data)
        if kind in self.MARKDOWN:
            folder, schema = self.MARKDOWN[kind]
            path = self.project.root / folder / f"{identifier}.md"
            if not path.is_file():
                raise ResearchFlowError(f"Record not found: {identifier}")
            data, body = read_markdown_record(path)
            if schema in {"problem", "gap", "claim", "observation", "hypothesis", "decision", "paper"}:
                validate_record(schema, data)
            return self._resolved(identifier, kind, path, data, body)
        if kind in self.YAML:
            folder, schema = self.YAML[kind]
            path = self.project.root / folder / f"{identifier}.yaml"
            if not path.is_file():
                raise ResearchFlowError(f"Record not found: {identifier}")
            data = read_yaml(path)
            validate_record(schema, data)
            return self._resolved(identifier, kind, path, data)
        raise ResearchFlowError(f"Unsupported EvidenceGraph record ID: {identifier}")

    def exists(self, identifier: str) -> bool:
        try:
            self.resolve(identifier)
            return True
        except ResearchFlowError:
            return False

    def _resolved(
        self, identifier: str, kind: str, path: Path, data: dict[str, Any], body: str | None = None
    ) -> dict[str, Any]:
        if data.get("id") != identifier:
            raise ResearchFlowError(f"Record ID does not match its path: {identifier} ({path})")
        payload: dict[str, Any] = {"metadata": data}
        if body is not None:
            payload["body"] = body
        return {
            "id": identifier,
            "kind": kind,
            "path": path.resolve().relative_to(self.project.root.resolve()).as_posix(),
            "data": data,
            "body": body,
            "fingerprint": _canonical_hash(payload),
        }


class ProblemStore:
    def __init__(self, project):
        self.project = project
        self.folder = project.root / "memory" / "problems"

    def _requests(self, path: Path) -> dict[str, Any]:
        request = read_yaml(path.expanduser().resolve())
        validate_record("problem_request", request)
        if request.get("supersedes") and not RecordResolver(self.project).exists(request["supersedes"]):
            raise ResearchFlowError(f"Problem supersedes missing record: {request['supersedes']}")
        return request

    def preflight(self, path: Path) -> dict[str, Any]:
        request = self._requests(path)
        fingerprint = _canonical_hash(request)
        existing = next((item for item in self.list() if item["request_fingerprint"] == fingerprint), None)
        return {
            "valid": True,
            "kind": "problem",
            "request_fingerprint": fingerprint,
            "idempotent_existing_id": existing["id"] if existing else None,
            "meaning": "Problem structure is valid; this does not establish a research gap or scientific claim.",
        }

    def add_file(self, path: Path, *, dry_run: bool = False) -> dict[str, Any]:
        request = self._requests(path)
        fingerprint = _canonical_hash(request)
        existing = next((item for item in self.list() if item["request_fingerprint"] == fingerprint), None)
        if existing:
            return {"problem": existing, "created": False, "idempotent": True, "dry_run": dry_run}
        if dry_run:
            return {"created": False, "idempotent": False, "dry_run": True, "request_fingerprint": fingerprint}
        with exclusive_lock(self.project.root / ".locks/problem-write.lock"):
            existing = next((item for item in self.list() if item["request_fingerprint"] == fingerprint), None)
            if existing:
                return {"problem": existing, "created": False, "idempotent": True, "dry_run": False}
            identifier = allocate_id(research_home(), "PROB")
            body = request.pop("body", "").strip() or self._body(request)
            metadata = {
                "schema_version": 1,
                "id": identifier,
                **request,
                "created_at": utc_now(),
                "request_fingerprint": fingerprint,
            }
            validate_record("problem", metadata)
            atomic_text(self.folder / f"{identifier}.md", markdown_record(metadata, body))
            return {"problem": metadata, "created": True, "idempotent": False, "dry_run": False}

    def list(self) -> list[dict[str, Any]]:
        values = []
        for path in sorted(self.folder.glob("PROB-*.md")):
            metadata, _ = read_markdown_record(path)
            validate_record("problem", metadata)
            values.append(metadata)
        return values

    def show(self, identifier: str) -> dict[str, Any]:
        resolved = RecordResolver(self.project).resolve(identifier)
        if resolved["kind"] != "PROB":
            raise ResearchFlowError(f"Not a Problem record: {identifier}")
        return {"metadata": resolved["data"], "body": resolved["body"], "fingerprint": resolved["fingerprint"]}

    @staticmethod
    def _body(request: dict[str, Any]) -> str:
        constraints = "\n".join(f"- {item}" for item in request["constraints"]) or "- None recorded."
        return (
            f"# {request['title']}\n\n## Objective\n\n{request['objective']}\n\n"
            f"## Scope\n\n{request['scope']}\n\n## Constraints\n\n{constraints}\n\n"
            f"## Application Context\n\n{request['application_context']}\n\n"
            "## Epistemic Boundary\n\nA Problem defines research scope; it is not evidence that a Gap is open."
        )


class ClaimStore:
    def __init__(self, project):
        self.project = project
        self.folder = project.root / "memory" / "claims"

    def _request(self, path: Path) -> dict[str, Any]:
        request = read_yaml(path.expanduser().resolve())
        validate_record("claim_request", request)
        overlap = set(request["supporting_findings"]) & set(request["counter_findings"])
        if overlap:
            raise ResearchFlowError(f"A Finding cannot both support and counter the same Claim: {', '.join(sorted(overlap))}")
        if request.get("supersedes") and not RecordResolver(self.project).exists(request["supersedes"]):
            raise ResearchFlowError(f"Claim supersedes missing record: {request['supersedes']}")
        self._validate_findings(request)
        self._validate_metrics(request)
        return request

    def _validate_findings(self, request: dict[str, Any]) -> None:
        resolver = RecordResolver(self.project)
        run_ids = {item["run_id"] for item in request["metric_evidence"]}
        for identifier in [*request["supporting_findings"], *request["counter_findings"]]:
            finding = resolver.resolve(identifier)
            if finding["kind"] != "OBS" or finding["data"].get("type") != "experimental_result":
                raise ResearchFlowError(f"Claim Finding must be an experimental_result Observation: {identifier}")
            if identifier in request["supporting_findings"]:
                refs = set(finding["data"].get("evidence", {}).get("refs", []))
                if not refs & run_ids:
                    raise ResearchFlowError(f"Supporting Finding {identifier} does not reference a Claim metric RUN.")

    def _validate_metrics(self, request: dict[str, Any]) -> None:
        resolver = RecordResolver(self.project)
        artifacts = ArtifactStore(self.project)
        seen: set[tuple[str, str, str]] = set()
        for evidence in request["metric_evidence"]:
            key = (evidence["run_id"], evidence["artifact_id"], evidence["json_pointer"])
            if key in seen:
                raise ResearchFlowError(f"Duplicate metric evidence: {' / '.join(key)}")
            seen.add(key)
            run = resolver.resolve(evidence["run_id"])["data"]
            if run.get("status") != "succeeded":
                raise ResearchFlowError(f"Claim metric RUN is not succeeded: {evidence['run_id']}")
            artifact = artifacts.show(evidence["artifact_id"])
            verification = artifacts.verify(evidence["artifact_id"])["results"][0]
            if not verification["valid"] or artifact["sha256"] != evidence["artifact_sha256"]:
                raise ResearchFlowError(f"Claim metric Artifact hash or references are invalid: {evidence['artifact_id']}")
            lineage = set(artifact["derived_from"]) | set(artifact["evidence"])
            if evidence["run_id"] not in lineage:
                raise ResearchFlowError(
                    f"Claim metric Artifact {evidence['artifact_id']} is not linked to {evidence['run_id']}."
                )
            artifact_path = artifacts._registry_file(artifact["path"])
            try:
                document = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ResearchFlowError(f"Claim metric Artifact is not valid UTF-8 JSON: {artifact_path}") from exc
            actual = _json_pointer(document, evidence["json_pointer"])
            metric_path = _json_pointer_tokens(evidence["json_pointer"])
            alias = evidence.get("alias_map")
            metric_segments = metric_path[1:] if metric_path and metric_path[0] == "metrics" else metric_path
            if evidence["metric_id"] not in metric_segments:
                if not alias or alias["alias"] not in metric_segments:
                    raise ResearchFlowError(
                        f"Claim metric ID {evidence['metric_id']} does not occur as an exact JSON Pointer segment; "
                        "a versioned alias map is required."
                    )
            if alias:
                alias_path = ArtifactStore(self.project)._registry_file(alias["path"])
                if not alias_path.is_file():
                    raise ResearchFlowError(f"Metric alias map does not exist: {alias['path']}")
                alias_sha = hashlib.sha256(alias_path.read_bytes()).hexdigest()
                alias_record = read_yaml(alias_path)
                validate_record("metric_alias_map", alias_record)
                if alias_sha != alias["sha256"] or alias_record["version"] != alias["version"]:
                    raise ResearchFlowError("Metric alias map fingerprint or version does not match the Claim.")
                if alias["alias"] not in alias_record["aliases"].get(evidence["metric_id"], []):
                    raise ResearchFlowError(
                        f"Metric alias {alias['alias']} is not registered for {evidence['metric_id']}."
                    )
            tolerance = float(evidence.get("tolerance", 0.0))
            if tolerance:
                if not isinstance(actual, (int, float)) or isinstance(actual, bool) or not isinstance(evidence["value"], (int, float)) or isinstance(evidence["value"], bool):
                    raise ResearchFlowError("Metric tolerance is valid only for numeric values.")
                experiment_id = run.get("experiment")
                experiment = resolver.resolve(experiment_id)["data"] if experiment_id else {}
                declared = experiment.get("metrics", {}).get("guardrails", {}).get("metric_tolerances", {}).get(evidence["metric_id"])
                if declared != tolerance:
                    raise ResearchFlowError(
                        f"Metric tolerance {tolerance} was not predeclared for {evidence['metric_id']} in {experiment_id}."
                    )
            if not _metric_values_equal(actual, evidence["value"], tolerance):
                raise ResearchFlowError(
                    f"Claim metric value mismatch at {evidence['json_pointer']}: expected {evidence['value']!r}, got {actual!r}"
                )

    def preflight(self, path: Path) -> dict[str, Any]:
        request = self._request(path)
        fingerprint = _canonical_hash(request)
        existing = next((item for item in self.list() if item["request_fingerprint"] == fingerprint), None)
        return {
            "valid": True,
            "kind": "claim",
            "request_fingerprint": fingerprint,
            "idempotent_existing_id": existing["id"] if existing else None,
            "meaning": "Claim structure, exact metric value, hashes, and references pass; semantic review, reproduction, and scientific establishment remain pending.",
        }

    def validate_current(self, metadata: dict[str, Any]) -> None:
        request = {
            key: metadata[key]
            for key in (
                "title", "statement", "scope", "qualifiers", "supporting_findings",
                "counter_findings", "metric_evidence", "status", "supersedes",
            )
        }
        if request["status"] != "draft":
            request["status"] = "draft"
        validate_record("claim_request", request)
        self._validate_findings(request)
        self._validate_metrics(request)

    def add_file(self, path: Path, *, dry_run: bool = False) -> dict[str, Any]:
        request = self._request(path)
        fingerprint = _canonical_hash(request)
        existing = next((item for item in self.list() if item["request_fingerprint"] == fingerprint), None)
        if existing:
            return {"claim": existing, "created": False, "idempotent": True, "dry_run": dry_run}
        if dry_run:
            return {"created": False, "idempotent": False, "dry_run": True, "request_fingerprint": fingerprint}
        with exclusive_lock(self.project.root / ".locks/claim-write.lock"):
            existing = next((item for item in self.list() if item["request_fingerprint"] == fingerprint), None)
            if existing:
                return {"claim": existing, "created": False, "idempotent": True, "dry_run": False}
            identifier = allocate_id(research_home(), "CLAIM")
            body = request.pop("body", "").strip() or self._body(request)
            metadata = {
                "schema_version": 1,
                "id": identifier,
                **request,
                "review": {"structural": "pending", "semantic": "pending", "reproduction": "not_checked"},
                "scientific_establishment": "not_established",
                "created_at": utc_now(),
                "request_fingerprint": fingerprint,
            }
            validate_record("claim", metadata)
            atomic_text(self.folder / f"{identifier}.md", markdown_record(metadata, body))
            return {"claim": metadata, "created": True, "idempotent": False, "dry_run": False}

    def list(self) -> list[dict[str, Any]]:
        values = []
        for path in sorted(self.folder.glob("CLAIM-*.md")):
            metadata, _ = read_markdown_record(path)
            validate_record("claim", metadata)
            values.append(metadata)
        return values

    def show(self, identifier: str) -> dict[str, Any]:
        resolved = RecordResolver(self.project).resolve(identifier)
        if resolved["kind"] != "CLAIM":
            raise ResearchFlowError(f"Not a Claim record: {identifier}")
        return {
            "metadata": resolved["data"],
            "body": resolved["body"],
            "fingerprint": resolved["fingerprint"],
            "graph": EvidenceGraphStore(self.project).claim_view(identifier),
        }

    def supersede_file(self, identifier: str, path: Path, *, dry_run: bool = False) -> dict[str, Any]:
        current = self.show(identifier)["metadata"]
        if current["status"] in {"superseded", "retracted"}:
            raise ResearchFlowError(f"Claim is not current and cannot be superseded: {identifier}")
        request = self._request(path)
        if request.get("supersedes") != identifier:
            raise ResearchFlowError(f"Replacement Claim must declare supersedes: {identifier}")
        if dry_run:
            return {**self.add_file(path, dry_run=True), "supersedes": identifier}
        with exclusive_lock(self.project.root / ".locks/claim-supersede.lock"):
            old_path = self.folder / f"{identifier}.md"
            old_bytes = old_path.read_bytes()
            old_metadata, old_body = read_markdown_record(old_path)
            if old_metadata["status"] in {"superseded", "retracted"}:
                raise ResearchFlowError(f"Claim is not current and cannot be superseded: {identifier}")
            created = self.add_file(path)
            replacement_id = created["claim"]["id"]
            try:
                old_metadata["status"] = "superseded"
                validate_record("claim", old_metadata)
                atomic_text(old_path, markdown_record(old_metadata, old_body))
            except Exception:
                atomic_text(old_path, old_bytes.decode("utf-8"))
                if created.get("created"):
                    (self.folder / f"{replacement_id}.md").unlink(missing_ok=True)
                raise
            return {**created, "supersedes": identifier}

    @staticmethod
    def _body(request: dict[str, Any]) -> str:
        qualifiers = "\n".join(f"- {item}" for item in request["qualifiers"])
        supporting = "\n".join(f"- {item}" for item in request["supporting_findings"])
        counter = "\n".join(f"- {item}" for item in request["counter_findings"]) or "- None recorded."
        return (
            f"# {request['title']}\n\n## Claim\n\n{request['statement']}\n\n"
            f"## Qualifiers\n\n{qualifiers}\n\n## Supporting Findings\n\n{supporting}\n\n"
            f"## Counter Findings\n\n{counter}\n\n"
            "## Epistemic Boundary\n\nDraft Claim; structural checks do not establish semantic validity, reproduction, or scientific truth."
        )


class EvidenceGraphStore:
    def __init__(self, project):
        self.project = project
        self.path = project.root / GRAPH_RELATIVE_PATH
        self.index_path = project.root / INDEX_RELATIVE_PATH
        self.audit_folder = project.root / AUDIT_RELATIVE_PATH
        self.resolver = RecordResolver(project)

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"schema_version": 1, "graph_id": "project-evidence-graph", "edges": [], "updated_at": utc_now()}

    def initialize(self) -> Path:
        with exclusive_lock(self.project.root / LOCK_RELATIVE_PATH):
            if not self.path.exists():
                self._write(self._empty())
        return self.path

    def load(self) -> dict[str, Any]:
        ledger = read_yaml(self.path) if self.path.exists() else self._empty()
        validate_record("evidence_graph", ledger)
        identifiers = [item["id"] for item in ledger["edges"]]
        if len(identifiers) != len(set(identifiers)):
            raise ResearchFlowError("EvidenceGraph contains duplicate edge IDs.")
        return ledger

    def _write(self, ledger: dict[str, Any]) -> None:
        candidate = {**ledger, "updated_at": utc_now()}
        validate_record("evidence_graph", candidate)
        write_yaml(self.path, candidate)

    def connect(
        self,
        source: str,
        relation: str,
        target: str,
        *,
        provenance_refs: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if dry_run:
            return self._connect(source, relation, target, provenance_refs or [], dry_run=True)
        with exclusive_lock(self.project.root / LOCK_RELATIVE_PATH):
            return self._connect(source, relation, target, provenance_refs or [], dry_run=False)

    def _connect(
        self, source: str, relation: str, target: str, provenance_refs: list[str], *, dry_run: bool
    ) -> dict[str, Any]:
        source_record = self.resolver.resolve(source)
        target_record = self.resolver.resolve(target)
        for ref in provenance_refs:
            self.resolver.resolve(ref)
        self._require_relation(source_record["kind"], relation, target_record["kind"])
        fingerprints = {source: source_record["fingerprint"], target: target_record["fingerprint"]}
        edge_hash = _canonical_hash({"from": source, "relation": relation, "to": target, "source_fingerprints": fingerprints})
        edge = {
            "id": f"EDGE-{edge_hash[:16]}",
            "from": source,
            "relation": relation,
            "to": target,
            "provenance_refs": provenance_refs,
            "status": "active",
            "source_fingerprints": fingerprints,
            "created_at": utc_now(),
            "supersedes": None,
        }
        ledger = self.load()
        existing = next((item for item in ledger["edges"] if item["id"] == edge["id"]), None)
        if existing:
            if existing["provenance_refs"] != provenance_refs:
                raise ResearchFlowError(
                    f"EvidenceGraph edge {existing['id']} already exists with different provenance."
                )
            return {"edge": existing, "created": False, "idempotent": True, "dry_run": dry_run}
        replaced = [
            item for item in ledger["edges"]
            if item["status"] == "active"
            and (item["from"], item["relation"], item["to"]) == (source, relation, target)
        ]
        if len(replaced) > 1:
            raise ResearchFlowError(f"EvidenceGraph has multiple active versions of {source} -[{relation}]-> {target}.")
        if replaced:
            edge["supersedes"] = replaced[0]["id"]
        previous = [
            {**item, "status": "superseded"} if replaced and item["id"] == replaced[0]["id"] else item
            for item in ledger["edges"]
        ]
        candidate = {**ledger, "edges": [*previous, edge]}
        validate_record("evidence_graph", candidate)
        issues = self._edge_issues(edge)
        if issues:
            raise ResearchFlowError("EvidenceGraph edge rejected: " + "; ".join(issues))
        cycle = self._dependency_cycle(candidate["edges"])
        if cycle:
            raise ResearchFlowError(f"EvidenceGraph dependency cycle detected: {' -> '.join(cycle)}")
        if not dry_run:
            self._write(candidate)
        return {
            "edge": edge,
            "created": not dry_run,
            "idempotent": False,
            "dry_run": dry_run,
            "superseded_edge": replaced[0]["id"] if replaced else None,
        }

    @staticmethod
    def _require_relation(source_kind: str, relation: str, target_kind: str) -> None:
        allowed = ALLOWED_RELATIONS.get(relation)
        if not allowed:
            raise ResearchFlowError(f"Unknown EvidenceGraph relation: {relation}")
        if source_kind not in allowed[0] or target_kind not in allowed[1]:
            raise ResearchFlowError(f"Invalid EvidenceGraph endpoints: {source_kind} -[{relation}]-> {target_kind}")

    def _edge_issues(self, edge: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        if edge["from"] == edge["to"]:
            issues.append(f"{edge['id']} is a self-loop")
            return issues
        try:
            source = self.resolver.resolve(edge["from"])
            target = self.resolver.resolve(edge["to"])
            self._require_relation(source["kind"], edge["relation"], target["kind"])
        except ResearchFlowError as exc:
            return [f"{edge['id']}: {exc}"]
        if set(edge["source_fingerprints"]) != {edge["from"], edge["to"]}:
            issues.append(f"{edge['id']} source_fingerprints must contain exactly both endpoints")
        for record in (source, target):
            if edge["source_fingerprints"].get(record["id"]) != record["fingerprint"]:
                issues.append(f"{edge['id']} is stale at {record['id']}")
        for ref in edge["provenance_refs"]:
            if not self.resolver.exists(ref):
                issues.append(f"{edge['id']} has unresolved provenance {ref}")
        relation = edge["relation"]
        if relation == "identifies" and target["data"].get("problem_id") != source["id"]:
            issues.append(f"{edge['id']} conflicts with Gap problem_id")
        elif relation == "motivates":
            from .corpus_gap import GapStore
            gap = GapStore(self.project).show(source["id"])
            if not gap["approved"]:
                issues.append(f"{edge['id']} Gap is not currently human-approved")
            if source["id"] not in target["data"].get("based_on", {}).get("gaps", []):
                issues.append(f"{edge['id']} conflicts with Hypothesis gap reference")
        elif relation == "tested_by":
            if target["data"].get("hypothesis", {}).get("id") != source["id"]:
                issues.append(f"{edge['id']} conflicts with Experiment hypothesis reference")
            falsification = (source.get("body") or "").split("## Falsification Condition", 1)
            if len(falsification) != 2 or not falsification[1].strip() or "Not yet specified" in falsification[1]:
                issues.append(f"{edge['id']} Hypothesis has no concrete falsification condition")
        elif relation == "produces":
            run_refs = target["data"].get("evidence", {}).get("refs", [])
            matching = False
            for ref in run_refs:
                if _prefix(ref) == "RUN" and self.resolver.exists(ref):
                    run = self.resolver.resolve(ref)["data"]
                    if run.get("experiment") == source["id"] and run.get("status") == "succeeded":
                        matching = True
                        break
            if not matching:
                issues.append(f"{edge['id']} Finding has no RUN for {source['id']}")
        elif relation in {"supports", "weakens", "contradicts"}:
            if source["data"].get("type") != "experimental_result":
                issues.append(f"{edge['id']} Claim relation source is not an experimental_result Finding")
            field = "supporting_findings" if relation == "supports" else "counter_findings"
            if source["id"] not in target["data"].get(field, []):
                issues.append(f"{edge['id']} conflicts with Claim {field}")
        elif relation == "substantiates":
            artifact_id = source["id"]
            verification = ArtifactStore(self.project).verify(artifact_id)["results"][0]
            if not verification["valid"]:
                issues.append(f"{edge['id']} Artifact integrity or references are invalid")
            if target["kind"] == "OBS":
                if artifact_id not in target["data"].get("evidence", {}).get("refs", []):
                    issues.append(f"{edge['id']} Artifact is not referenced by Finding")
            elif not any(item["artifact_id"] == artifact_id for item in target["data"].get("metric_evidence", [])):
                issues.append(f"{edge['id']} Artifact is not referenced by Claim metric evidence")
        elif relation in {"supports_gap", "weakens_gap"}:
            from .corpus_gap import CorpusStore
            corpus_id = target["data"].get("derivation", {}).get("corpus_id")
            try:
                corpus = CorpusStore(self.project).show(corpus_id)["record"]
            except ResearchFlowError as exc:
                issues.append(f"{edge['id']} Gap Corpus is invalid: {exc}")
            else:
                paper = next((item for item in corpus["papers"] if item["id"] == source["id"]), None)
                current = source["data"].get("source", {}).get("document", {}).get("sha256")
                if not paper or not current or paper["source_fingerprint"].casefold() != current.casefold():
                    issues.append(f"{edge['id']} Paper fingerprint is not bound to the Gap Corpus")
                if relation == "weakens_gap" and source["id"] not in {
                    item.get("ref") for item in target["data"].get("known_counterevidence", [])
                }:
                    issues.append(f"{edge['id']} Paper is not declared as Gap counterevidence")
        return issues

    def check(self) -> dict[str, Any]:
        ledger = self.load()
        issues: list[str] = []
        active_triples: set[tuple[str, str, str]] = set()
        for edge in ledger["edges"]:
            if edge["status"] != "active":
                continue
            triple = (edge["from"], edge["relation"], edge["to"])
            if triple in active_triples:
                issues.append(f"Duplicate active edge: {' '.join(triple)}")
            active_triples.add(triple)
            issues.extend(self._edge_issues(edge))
        cycle = self._dependency_cycle(ledger["edges"])
        if cycle:
            issues.append(f"Dependency cycle: {' -> '.join(cycle)}")
        claim_store = ClaimStore(self.project)
        claims = {}
        for item in claim_store.list():
            try:
                claim_store.validate_current(item)
            except ResearchFlowError as exc:
                issues.append(f"{item['id']} exact evidence check failed: {exc}")
            claims[item["id"]] = self.claim_view(item["id"], ledger=ledger)
        warnings = [] if self.path.exists() else ["EvidenceGraph is not initialized; run evidence graph rebuild to create it."]
        index = self.index_status(ledger=ledger)
        if self.path.exists() and not index["current"]:
            warnings.append("EvidenceGraph index is missing, invalid, or stale; run evidence graph rebuild.")
        return {
            "initialized": self.path.exists(),
            "valid": not issues,
            "ready": bool(self.path.exists()) and bool(claims) and not issues and all(
                item["evidence_ready"] for item in claims.values()
            ),
            "edges": len(ledger["edges"]),
            "claims": claims,
            "issues": issues,
            "warnings": warnings,
            "index": index,
            "meaning": "Deterministic structure and exact evidence checks only; semantic review, reproduction, and scientific truth remain separate.",
        }

    @staticmethod
    def _dependency_cycle(edges: list[dict[str, Any]]) -> list[str]:
        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            if edge["status"] == "active" and edge["relation"] in DEPENDENCY_RELATIONS:
                adjacency.setdefault(edge["from"], []).append(edge["to"])
        visiting: set[str] = set()
        visited: set[str] = set()
        trail: list[str] = []

        def visit(node: str) -> list[str] | None:
            if node in visiting:
                return trail[trail.index(node):] + [node]
            if node in visited:
                return None
            visiting.add(node)
            trail.append(node)
            for target in sorted(adjacency.get(node, [])):
                found = visit(target)
                if found:
                    return found
            trail.pop()
            visiting.remove(node)
            visited.add(node)
            return None

        for node in sorted(adjacency):
            found = visit(node)
            if found:
                return found
        return []

    def _latest_audit(self, claim_id: str, fingerprint: str) -> dict[str, Any] | None:
        matches = []
        for path in sorted(self.audit_folder.glob("EGAUDIT-*.yaml")):
            audit = read_yaml(path)
            validate_record("evidence_graph_audit", audit)
            if audit["target"] == claim_id and audit["target_fingerprint"] == fingerprint:
                matches.append(audit)
        return matches[-1] if matches else None

    def _claim_relevant_edges(self, claim_id: str, edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return only active edges that can affect one Claim's evidence decision."""
        relevant: dict[str, dict[str, Any]] = {}
        frontier = {claim_id}
        dependency_incoming = {"supports", "weakens", "contradicts", "substantiates", "produces", "tested_by"}
        while frontier:
            target = frontier.pop()
            for edge in edges:
                if edge["status"] != "active" or edge["to"] != target or edge["relation"] not in dependency_incoming:
                    continue
                if edge["id"] in relevant:
                    continue
                relevant[edge["id"]] = edge
                if edge["relation"] in {"supports", "weakens", "contradicts", "produces", "tested_by"}:
                    frontier.add(edge["from"])
        return [relevant[key] for key in sorted(relevant)]

    def claim_view(self, claim_id: str, *, ledger: dict[str, Any] | None = None) -> dict[str, Any]:
        claim = self.resolver.resolve(claim_id)
        if claim["kind"] != "CLAIM":
            raise ResearchFlowError(f"Not a Claim record: {claim_id}")
        edges = [item for item in (ledger or self.load())["edges"] if item["status"] == "active"]
        support_edges = [item for item in edges if item["to"] == claim_id and item["relation"] == "supports"]
        support_sources = {item["from"] for item in support_edges}
        missing_support = sorted(set(claim["data"]["supporting_findings"]) - support_sources)
        chains: list[list[str]] = []
        chain_issues: list[str] = []
        earliest: str | None = claim_id if missing_support else None
        for finding_id in claim["data"]["supporting_findings"]:
            produce_edges = [item for item in edges if item["to"] == finding_id and item["relation"] == "produces"]
            if not produce_edges:
                chain_issues.append(f"Missing Experiment -[produces]-> {finding_id}")
                earliest = earliest or finding_id
                continue
            for produce in produce_edges:
                experiment_id = produce["from"]
                test_edges = [item for item in edges if item["to"] == experiment_id and item["relation"] == "tested_by"]
                if not test_edges:
                    chain_issues.append(f"Missing Hypothesis -[tested_by]-> {experiment_id}")
                    earliest = earliest or experiment_id
                    continue
                for tested in test_edges:
                    chains.append([tested["from"], experiment_id, finding_id, claim_id])
        if missing_support:
            chain_issues.extend(f"Missing {item} -[supports]-> {claim_id}" for item in missing_support)
        relevant_edges = self._claim_relevant_edges(claim_id, edges)
        edge_issues = [issue for edge in relevant_edges for issue in self._edge_issues(edge)]
        try:
            ClaimStore(self.project).validate_current(claim["data"])
        except ResearchFlowError as exc:
            edge_issues.append(f"{claim_id} exact evidence check failed: {exc}")
        structural_ready = not missing_support and not chain_issues and not edge_issues and bool(chains)
        audit = self._latest_audit(claim_id, claim["fingerprint"])
        semantic = audit["semantic_review"]["status"] if audit else "pending"
        fidelity = audit["fidelity_review"]["status"] if audit else "pending"
        evidence_ready = structural_ready and semantic == "pass" and fidelity not in {"fail", "unavailable", "stale"}
        counter_edges = [
            {key: edge[key] for key in ("id", "from", "relation", "to", "source_fingerprints")}
            for edge in relevant_edges if edge["relation"] in {"weakens", "contradicts"}
        ]
        node_ids = sorted({value for edge in relevant_edges for value in (edge["from"], edge["to"])})
        fingerprints = {}
        for identifier in node_ids:
            try:
                fingerprints[identifier] = self.resolver.resolve(identifier)["fingerprint"]
            except ResearchFlowError:
                fingerprints[identifier] = None
        return {
            "claim_id": claim_id,
            "claim_fingerprint": claim["fingerprint"],
            "chains": chains,
            "shortest_support_chains": chains,
            "counterevidence_edges": counter_edges,
            "node_fingerprints": fingerprints,
            "structural_ready": structural_ready,
            "semantic_review": semantic,
            "fidelity_review": fidelity,
            "evidence_ready": evidence_ready,
            "earliest_weak_node": earliest,
            "issues": [*chain_issues, *edge_issues],
            "latest_audit": audit,
            "scientific_establishment": "not_established",
        }

    def review_input_fingerprint(self, claim_id: str) -> str:
        view = self.claim_view(claim_id)
        return _canonical_hash({
            "claim_id": claim_id,
            "claim_fingerprint": view["claim_fingerprint"],
            "chains": view["chains"],
            "counterevidence_edges": view["counterevidence_edges"],
            "node_fingerprints": view["node_fingerprints"],
        })

    def rebuild(self, *, dry_run: bool = False) -> dict[str, Any]:
        if dry_run:
            return self._rebuild(dry_run=True)
        with exclusive_lock(self.project.root / LOCK_RELATIVE_PATH):
            if not self.path.exists():
                self._write(self._empty())
            return self._rebuild(dry_run=False)

    def _rebuild(self, *, dry_run: bool) -> dict[str, Any]:
        ledger = self.load()
        check = self.check()
        if not check["valid"]:
            raise ResearchFlowError("Cannot rebuild invalid EvidenceGraph: " + "; ".join(check["issues"]))
        node_ids = sorted({value for edge in ledger["edges"] for value in (edge["from"], edge["to"], *edge["provenance_refs"])})
        nodes = []
        for identifier in node_ids:
            record = self.resolver.resolve(identifier)
            nodes.append({key: record[key] for key in ("id", "kind", "path", "fingerprint")})
        core = {
            "schema_version": 1,
            "graph_id": "project-evidence-graph",
            "nodes": nodes,
            "edges": sorted(ledger["edges"], key=lambda item: item["id"]),
        }
        index = {**core, "graph_fingerprint": _canonical_hash(core)}
        changed = True
        if self.index_path.exists():
            try:
                changed = json.loads(self.index_path.read_text(encoding="utf-8")) != index
            except (OSError, json.JSONDecodeError):
                changed = True
        if not dry_run:
            if changed:
                atomic_text(self.index_path, json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        return {
            "path": str(self.index_path),
            "changed": changed,
            "dry_run": dry_run,
            "nodes": len(nodes),
            "edges": len(ledger["edges"]),
            "graph_fingerprint": index["graph_fingerprint"],
            "authority": "derived_rebuildable_index",
        }

    def _index_document(self, ledger: dict[str, Any]) -> dict[str, Any]:
        node_ids = sorted({value for edge in ledger["edges"] for value in (edge["from"], edge["to"], *edge["provenance_refs"])})
        nodes = []
        for identifier in node_ids:
            record = self.resolver.resolve(identifier)
            nodes.append({key: record[key] for key in ("id", "kind", "path", "fingerprint")})
        core = {
            "schema_version": 1, "graph_id": "project-evidence-graph",
            "nodes": nodes, "edges": sorted(ledger["edges"], key=lambda item: item["id"]),
        }
        return {**core, "graph_fingerprint": _canonical_hash(core)}

    def index_status(self, *, ledger: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"exists": False, "current": False, "path": str(self.index_path), "graph_fingerprint": None}
        try:
            actual = json.loads(self.index_path.read_text(encoding="utf-8"))
            expected = self._index_document(ledger or self.load())
            return {
                "exists": True, "current": actual == expected, "path": str(self.index_path),
                "graph_fingerprint": actual.get("graph_fingerprint"),
            }
        except (OSError, json.JSONDecodeError, ResearchFlowError):
            return {"exists": True, "current": False, "path": str(self.index_path), "graph_fingerprint": None}

    def import_review(self, claim_id: str, review_file: Path, *, dry_run: bool = False) -> dict[str, Any]:
        request = read_yaml(review_file.expanduser().resolve())
        validate_record("evidence_graph_review_request", request)
        if request["target"] != claim_id:
            raise ResearchFlowError(f"Review targets {request['target']}, not {claim_id}.")
        view = self.claim_view(claim_id)
        if request["target_fingerprint"] != view["claim_fingerprint"]:
            raise ResearchFlowError("Semantic review target fingerprint is stale.")
        expected_input = self.review_input_fingerprint(claim_id)
        if request["provenance"]["input_fingerprint"] != expected_input:
            raise ResearchFlowError("Semantic review input fingerprint does not match the current Claim graph.")
        semantic = request["semantic_review"]
        if semantic["status"] == "pass" and (
            semantic["experiment_falsifiable"] != "pass" or semantic["claim_within_findings"] != "pass"
        ):
            raise ResearchFlowError("Semantic review cannot pass unless falsifiability and Claim scope both pass.")
        fidelity = request["fidelity_review"]
        if fidelity["status"] == "pass" and fidelity["failures"]:
            raise ResearchFlowError("Fidelity review cannot pass while M1-M5 failures are recorded.")
        if fidelity["status"] == "fail" and not fidelity["failures"]:
            raise ResearchFlowError("A failed fidelity review must name at least one M1-M5 failure.")
        relevant_issues = list(view["issues"])
        l1_pass = view["structural_ready"] and not relevant_issues
        semantic_status = semantic["status"] if l1_pass else "stale"
        overall = (
            "pass" if l1_pass and semantic_status == "pass" and fidelity["status"] not in {"fail", "unavailable"}
            else "fail" if not l1_pass or semantic_status == "fail" or fidelity["status"] == "fail"
            else "unavailable" if semantic_status == "unavailable" or fidelity["status"] == "unavailable"
            else "pending"
        )
        payload = {
            "schema_version": 1, "target": claim_id, "target_fingerprint": view["claim_fingerprint"],
            "mode": "full_chain",
            "deterministic_checks": {
                "status": "pass" if l1_pass else "fail",
                "checks": ["schema_valid", "refs_resolve", "edge_types_valid", "metric_values_match", "chain_complete"],
                "issues": relevant_issues,
            },
            "semantic_review": {
                "status": semantic_status, "reviewer": request["reviewer"], "rationale": semantic["rationale"],
            },
            "fidelity_review": {
                "status": fidelity["status"], "failures": fidelity["failures"], "rationale": fidelity["rationale"],
            },
            "review_provenance": request["provenance"],
            "earliest_weak_node": view["earliest_weak_node"],
            "repair_plan": {
                "allowed_actions": [] if overall == "pass" else ["review_semantics"] if l1_pass else ["add_missing_edge", "revise_protocol", "rerun_experiment", "narrow_claim"],
                "automatic_mutation": False,
            },
            "overall_status": overall, "created_at": utc_now(),
        }
        if dry_run:
            return {**payload, "id": None, "dry_run": True, "written": False}
        with exclusive_lock(self.project.root / LOCK_RELATIVE_PATH):
            current_view = self.claim_view(claim_id)
            if (
                current_view["claim_fingerprint"] != request["target_fingerprint"]
                or self.review_input_fingerprint(claim_id) != request["provenance"]["input_fingerprint"]
                or current_view["structural_ready"] != view["structural_ready"]
                or current_view["issues"] != view["issues"]
            ):
                raise ResearchFlowError("Claim or evidence inputs changed during review import; rerun preflight.")
            payload = {"id": allocate_id(research_home(), "EGAUDIT"), **payload}
            validate_record("evidence_graph_audit", payload)
            write_yaml(self.audit_folder / f"{payload['id']}.yaml", payload)
        return {**payload, "dry_run": False, "written": True}

    def export(self, output: Path, *, format: str = "dot", dry_run: bool = False) -> dict[str, Any]:
        ledger = self.load()
        check = self.check()
        if not check["valid"]:
            raise ResearchFlowError("Cannot export invalid EvidenceGraph: " + "; ".join(check["issues"]))
        if format == "json":
            text = json.dumps(self._index_document(ledger), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        elif format == "dot":
            lines = ["digraph EvidenceGraph {", "  rankdir=LR;"]
            for edge in sorted((item for item in ledger["edges"] if item["status"] == "active"), key=lambda item: item["id"]):
                source = edge["from"].replace('"', '\\"')
                target = edge["to"].replace('"', '\\"')
                relation = edge["relation"].replace('"', '\\"')
                lines.append(f'  "{source}" -> "{target}" [label="{relation}"];')
            lines.append("}")
            text = "\n".join(lines) + "\n"
        else:
            raise ResearchFlowError("EvidenceGraph export format must be dot or json.")
        target = output.expanduser().resolve()
        try:
            target.relative_to(self.project.root.resolve())
        except ValueError as exc:
            raise ResearchFlowError("EvidenceGraph export output must stay inside the project workspace.") from exc
        changed = not target.exists() or target.read_text(encoding="utf-8") != text
        if changed and not dry_run:
            atomic_text(target, text)
        return {"path": str(target), "format": format, "changed": changed, "dry_run": dry_run}

    def audit(self, claim_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        if dry_run:
            return self._audit(claim_id, dry_run=True)
        with exclusive_lock(self.project.root / LOCK_RELATIVE_PATH):
            return self._audit(claim_id, dry_run=False)

    def _audit(self, claim_id: str, *, dry_run: bool) -> dict[str, Any]:
        view = self.claim_view(claim_id)
        relevant_issues = list(view["issues"])
        l1_pass = view["structural_ready"] and not relevant_issues
        payload = {
            "schema_version": 1,
            "target": claim_id,
            "target_fingerprint": view["claim_fingerprint"],
            "mode": "full_chain",
            "deterministic_checks": {
                "status": "pass" if l1_pass else "fail",
                "checks": ["schema_valid", "refs_resolve", "edge_types_valid", "metric_values_match", "chain_complete"],
                "issues": relevant_issues,
            },
            "semantic_review": {"status": "pending", "reviewer": None, "rationale": None},
            "fidelity_review": {"status": "pending", "failures": [], "rationale": "Not checked in the deterministic L1 audit."},
            "review_provenance": None,
            "earliest_weak_node": view["earliest_weak_node"],
            "repair_plan": {
                "allowed_actions": ["review_semantics"] if l1_pass else ["add_missing_edge", "revise_protocol", "rerun_experiment", "narrow_claim"],
                "automatic_mutation": False,
            },
            "overall_status": "pending" if l1_pass else "fail",
            "created_at": utc_now(),
        }
        if dry_run:
            return {**payload, "id": None, "dry_run": True, "written": False}
        payload = {"id": allocate_id(research_home(), "EGAUDIT"), **payload}
        validate_record("evidence_graph_audit", payload)
        write_yaml(self.audit_folder / f"{payload['id']}.yaml", payload)
        return {**payload, "dry_run": False, "written": True}

    def summary(self) -> dict[str, Any]:
        check = self.check()
        return {
            "initialized": check["initialized"],
            "valid": check["valid"],
            "ready": check["ready"],
            "edges": check["edges"],
            "claims": len(check["claims"]),
            "evidence_ready_claims": sum(1 for item in check["claims"].values() if item["evidence_ready"]),
            "pending_or_blocked_claims": sorted(
                identifier for identifier, item in check["claims"].items() if not item["evidence_ready"]
            ),
            "issues": check["issues"],
            "warnings": check["warnings"],
        }
