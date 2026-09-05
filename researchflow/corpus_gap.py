from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from .config import research_home
from .errors import ResearchFlowError
from .ids import allocate_id
from .io import atomic_text, exclusive_lock, markdown_record, read_markdown_record, read_yaml, utc_now, write_yaml
from .literature import LiteratureMatrixStore
from .review import matrix_fingerprint, paper_verification
from .schema import validate_record


NODE_TYPES = {
    "Paper", "Method", "Task", "Dataset", "Metric", "Assumption",
    "Result", "Limitation", "FailureCondition",
}
TUPLE_RELATIONS = {
    "proposes", "evaluated_on", "uses_dataset", "measured_by", "improves_over",
    "fails_under", "assumes", "limited_by", "contradicts",
}
MOTIFS = {
    "missing_edge", "assumption_failure", "evaluation_blind_spot",
    "contradictory_results", "dataset_method_mismatch",
}


def canonical_hash(value: Any) -> str:
    import hashlib

    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _safe_workspace_path(project, value: str) -> str:
    if not value or "\\" in value or "\x00" in value:
        raise ResearchFlowError(f"Unsafe workspace-relative locator path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value or ".." in pure.parts or any(":" in part for part in pure.parts):
        raise ResearchFlowError(f"Unsafe workspace-relative locator path: {value!r}")
    root = project.root.resolve()
    resolved = root.joinpath(*pure.parts).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ResearchFlowError(f"Extraction locator escapes the project workspace: {value}") from exc
    if not resolved.is_file():
        raise ResearchFlowError(f"Extraction locator path does not exist: {value}")
    return pure.as_posix()


def _paper_source(project, paper_id: str) -> tuple[dict[str, Any], str, str]:
    result = project.evidence.show(paper_id)
    metadata, body = result["metadata"], result["body"]
    verification = paper_verification(metadata)
    source = metadata.get("source", {}).get("document", {})
    fingerprint = str(source.get("sha256") or "")
    if not verification["source_verified"] or not verification["fingerprint_verified"] or not fingerprint:
        raise ResearchFlowError(f"Corpus requires a source/fingerprint-verified paper: {paper_id}")
    return metadata, body, fingerprint


def corpus_fingerprint(scope: dict[str, Any], matrix_sha256: str, papers: list[dict[str, Any]]) -> str:
    stable_papers = sorted(
        ({"id": item["id"], "source_fingerprint": item["source_fingerprint"]} for item in papers),
        key=lambda item: item["id"],
    )
    return canonical_hash({"scope": scope, "matrix_sha256": matrix_sha256, "papers": stable_papers})


def extraction_fingerprint(record: dict[str, Any]) -> str:
    return canonical_hash({
        key: record[key]
        for key in ("corpus_id", "paper_id", "paper_fingerprint", "extractor", "tuples")
    })


def gap_fingerprint(record: dict[str, Any]) -> str:
    derivation = dict(record["derivation"])
    derivation.pop("cgap_run_id", None)
    return canonical_hash({
        key: record[key]
        for key in (
            "title", "problem_id", "statement", "mechanism_missing", "remaining_scope",
            "boundary_conditions", "known_counterevidence", "falsification", "scores", "supersedes",
        )
    } | {"derivation": derivation})


class CorpusStore:
    def __init__(self, project):
        self.project = project
        self.folder = project.root / "evidence" / "corpora"
        self.extraction_root = project.root / "evidence" / "corpus-extractions"

    def _candidate(
        self,
        *,
        title: str,
        matrix_id: str,
        scope_file: Path,
        created_by: str,
        supersedes: str | None,
    ) -> dict[str, Any]:
        scope = read_yaml(scope_file.expanduser().resolve())
        validate_record("corpus_scope", scope)
        matrix = LiteratureMatrixStore(self.project).load()
        if matrix["id"] != matrix_id:
            raise ResearchFlowError(f"Selected matrix is {matrix['id']}, not {matrix_id}.")
        matrix_sha = matrix_fingerprint(matrix)
        papers = []
        for entry in sorted(matrix["papers"], key=lambda item: item["paper_id"]):
            if entry.get("decision") == "exclude":
                continue
            metadata, _, fingerprint = _paper_source(self.project, entry["paper_id"])
            if entry["source_sha256"].casefold() != fingerprint.casefold():
                raise ResearchFlowError(f"Matrix source fingerprint is stale for {entry['paper_id']}.")
            verification = paper_verification(metadata)
            papers.append({
                "id": entry["paper_id"],
                "source_fingerprint": fingerprint,
                "review_status": "human_reviewed" if verification["human_reviewed"] else "verified",
            })
        if not papers:
            raise ResearchFlowError("Corpus needs at least one non-excluded verified paper from the selected matrix.")
        if supersedes:
            old = self.show(supersedes)["record"]
            if old["id"] != supersedes:
                raise ResearchFlowError(f"Corpus supersedes record is invalid: {supersedes}")
        fingerprint = corpus_fingerprint(scope, matrix_sha, papers)
        return {
            "title": title.strip(), "scope": scope,
            "source_matrix": {"id": matrix_id, "sha256": matrix_sha},
            "papers": papers, "created_by": created_by.strip(),
            "corpus_fingerprint": fingerprint, "supersedes": supersedes,
        }

    def create(
        self,
        *,
        title: str,
        matrix_id: str,
        scope_file: Path,
        created_by: str = "agent",
        supersedes: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        candidate = self._candidate(
            title=title, matrix_id=matrix_id, scope_file=scope_file,
            created_by=created_by, supersedes=supersedes,
        )
        existing = next((item for item in self.list() if item["corpus_fingerprint"] == candidate["corpus_fingerprint"]), None)
        if existing:
            return {"corpus": existing, "created": False, "idempotent": True, "dry_run": dry_run}
        if dry_run:
            return {"created": False, "idempotent": False, "dry_run": True, **candidate}
        with exclusive_lock(self.project.root / ".locks/corpus-write.lock"):
            existing = next((item for item in self.list() if item["corpus_fingerprint"] == candidate["corpus_fingerprint"]), None)
            if existing:
                return {"corpus": existing, "created": False, "idempotent": True, "dry_run": False}
            record = {
                "schema_version": 1, "id": allocate_id(research_home(), "CORPUS"),
                **candidate, "created_at": utc_now(),
            }
            validate_record("corpus", record)
            write_yaml(self.folder / f"{record['id']}.yaml", record)
            return {"corpus": record, "created": True, "idempotent": False, "dry_run": False}

    def list(self) -> list[dict[str, Any]]:
        result = []
        for path in sorted(self.folder.glob("CORPUS-*.yaml")):
            record = read_yaml(path)
            validate_record("corpus", record)
            result.append(record)
        return result

    def show(self, corpus_id: str) -> dict[str, Any]:
        path = self.folder / f"{corpus_id}.yaml"
        record = read_yaml(path)
        validate_record("corpus", record)
        if record["id"] != corpus_id:
            raise ResearchFlowError(f"Corpus ID does not match path: {corpus_id}")
        return {"record": record, "verification": self.verify(corpus_id)}

    def verify(self, corpus_id: str) -> dict[str, Any]:
        path = self.folder / f"{corpus_id}.yaml"
        record = read_yaml(path)
        validate_record("corpus", record)
        issues: list[str] = []
        expected = corpus_fingerprint(record["scope"], record["source_matrix"]["sha256"], record["papers"])
        if expected != record["corpus_fingerprint"]:
            issues.append("corpus fingerprint does not match the frozen content")
        ids = [item["id"] for item in record["papers"]]
        if ids != sorted(set(ids)):
            issues.append("paper IDs must be unique and sorted")
        stale_papers = []
        for item in record["papers"]:
            try:
                _, _, current = _paper_source(self.project, item["id"])
                if current.casefold() != item["source_fingerprint"].casefold():
                    stale_papers.append(item["id"])
            except ResearchFlowError:
                stale_papers.append(item["id"])
        if stale_papers:
            issues.append("paper source changed or is unavailable: " + ", ".join(stale_papers))
        matrix_current = None
        try:
            matrix = LiteratureMatrixStore(self.project).load()
            if matrix["id"] == record["source_matrix"]["id"]:
                matrix_current = matrix_fingerprint(matrix) == record["source_matrix"]["sha256"]
        except ResearchFlowError:
            matrix_current = False
        return {
            "corpus_id": corpus_id, "valid": not issues, "issues": issues,
            "frozen": True, "paper_sources_current": not stale_papers,
            "source_matrix_current": matrix_current,
            "meaning": "A valid Corpus is a frozen source snapshot; it does not prove that a research Gap is open.",
        }

    def _normalize_extraction(self, request_file: Path) -> dict[str, Any]:
        request = read_yaml(request_file.expanduser().resolve())
        validate_record("corpus_extraction_request", request)
        corpus = self.show(request["corpus_id"])["record"]
        paper = next((item for item in corpus["papers"] if item["id"] == request["paper_id"]), None)
        if not paper:
            raise ResearchFlowError(f"{request['paper_id']} is not part of {request['corpus_id']}.")
        if request["paper_fingerprint"].casefold() != paper["source_fingerprint"].casefold():
            raise ResearchFlowError("Extraction paper fingerprint does not match the frozen Corpus.")
        _, body, current = _paper_source(self.project, request["paper_id"])
        if current.casefold() != request["paper_fingerprint"].casefold():
            raise ResearchFlowError("Extraction paper fingerprint is stale against the current Paper.")
        normalized = dict(request)
        tuples = []
        tuple_ids: set[str] = set()
        for item in request["tuples"]:
            if "id" in item:
                raise ResearchFlowError("Extraction requests must not supply tuple IDs; ResearchFlow derives stable IDs.")
            for claim_id in item["evidence"]["paper_claim_ids"]:
                if claim_id not in body:
                    raise ResearchFlowError(f"Extraction references missing paper claim {claim_id} in {request['paper_id']}.")
            for locator in item["evidence"]["locators"]:
                if locator["kind"] == "path":
                    _safe_workspace_path(self.project, locator["value"])
            tuple_id = f"TUPLE-{canonical_hash({'corpus': request['corpus_id'], 'paper': request['paper_id'], 'tuple': item})[:12]}"
            if tuple_id in tuple_ids:
                raise ResearchFlowError(f"Duplicate extraction tuple: {tuple_id}")
            tuple_ids.add(tuple_id)
            tuples.append({"id": tuple_id, **item})
        normalized["tuples"] = tuples
        return normalized

    def preflight_extraction(self, request_file: Path) -> dict[str, Any]:
        normalized = self._normalize_extraction(request_file)
        fingerprint = extraction_fingerprint(normalized)
        target = self.extraction_root / normalized["corpus_id"] / f"{normalized['paper_id']}.yaml"
        existing = read_yaml(target) if target.exists() else None
        return {
            "valid": True, "extraction_fingerprint": fingerprint,
            "idempotent": bool(existing and existing.get("extraction_fingerprint") == fingerprint),
            "target": target.relative_to(self.project.root).as_posix(),
            "meaning": "Extraction structure and source locators pass; semantic interpretation remains review-pending.",
        }

    def add_extraction(self, request_file: Path, *, dry_run: bool = False) -> dict[str, Any]:
        normalized = self._normalize_extraction(request_file)
        fingerprint = extraction_fingerprint(normalized)
        target = self.extraction_root / normalized["corpus_id"] / f"{normalized['paper_id']}.yaml"
        if target.exists():
            existing = read_yaml(target)
            if existing.get("extraction_fingerprint") == fingerprint:
                return {"extraction": existing, "created": False, "idempotent": True, "dry_run": dry_run}
            raise ResearchFlowError(
                f"Extraction already exists with different content: {target}. Create a new Corpus instead of overwriting it."
            )
        if dry_run:
            return {"created": False, "idempotent": False, "dry_run": True, "extraction_fingerprint": fingerprint}
        with exclusive_lock(self.project.root / ".locks/corpus-extraction-write.lock"):
            if target.exists():
                existing = read_yaml(target)
                if existing.get("extraction_fingerprint") == fingerprint:
                    return {"extraction": existing, "created": False, "idempotent": True, "dry_run": False}
                raise ResearchFlowError(f"Extraction changed during import: {target}")
            record = {
                "schema_version": 1, **normalized, "extraction_fingerprint": fingerprint,
                "created_at": utc_now(),
                "review": {"status": "pending", "reviewer": None, "reviewed_fingerprint": None, "rationale": None, "reviewed_at": None},
                "reviews": [],
            }
            validate_record("corpus_extraction", record)
            write_yaml(target, record)
            return {"extraction": record, "created": True, "idempotent": False, "dry_run": False}

    def review_extraction(
        self, corpus_id: str, paper_id: str, *, decision: str, reviewer: str,
        rationale: str, dry_run: bool = False,
    ) -> dict[str, Any]:
        if decision not in {"accepted", "revision_requested", "rejected"}:
            raise ResearchFlowError("Extraction decision must be accepted, revision_requested, or rejected.")
        if decision == "accepted" and (
            not reviewer.startswith("human:") or not reviewer.removeprefix("human:").strip()
        ):
            raise ResearchFlowError("Only a human:* reviewer may accept a Corpus extraction.")
        if not reviewer.strip() or not rationale.strip():
            raise ResearchFlowError("Extraction review needs a reviewer and rationale.")
        target = self.extraction_root / corpus_id / f"{paper_id}.yaml"
        def prepare() -> tuple[dict[str, Any], dict[str, Any]]:
            record = read_yaml(target)
            validate_record("corpus_extraction", record)
            current = extraction_fingerprint(record)
            if current != record["extraction_fingerprint"]:
                raise ResearchFlowError("Extraction content changed; import a new Corpus/extraction instead of reviewing stale content.")
            review = {
                "status": decision, "reviewer": reviewer.strip(), "reviewed_fingerprint": current,
                "rationale": rationale.strip(), "reviewed_at": utc_now(),
            }
            candidate = {**record, "review": review, "reviews": [*record["reviews"], review]}
            validate_record("corpus_extraction", candidate)
            return review, candidate

        if dry_run:
            review, _ = prepare()
        else:
            with exclusive_lock(self.project.root / ".locks/corpus-extraction-write.lock"):
                review, candidate = prepare()
                write_yaml(target, candidate)
        return {"corpus_id": corpus_id, "paper_id": paper_id, "review": review, "dry_run": dry_run}

    def extraction_status(self, corpus_id: str) -> dict[str, Any]:
        corpus = self.show(corpus_id)["record"]
        values = []
        for paper in corpus["papers"]:
            path = self.extraction_root / corpus_id / f"{paper['id']}.yaml"
            if not path.exists():
                values.append({"paper_id": paper["id"], "status": "missing", "current": False})
                continue
            record = read_yaml(path)
            validate_record("corpus_extraction", record)
            current = extraction_fingerprint(record) == record["extraction_fingerprint"]
            accepted = (
                current and record["review"]["status"] == "accepted"
                and record["review"]["reviewed_fingerprint"] == record["extraction_fingerprint"]
            )
            values.append({
                "paper_id": paper["id"], "status": record["review"]["status"],
                "current": current, "accepted": accepted,
            })
        return {
            "corpus_id": corpus_id, "papers": len(corpus["papers"]), "extractions": values,
            "complete_and_reviewed": bool(values) and all(item.get("accepted", False) for item in values),
        }

    def scaffold_extraction(self, corpus_id: str, paper_id: str, output: Path) -> Path:
        corpus = self.show(corpus_id)["record"]
        paper = next((item for item in corpus["papers"] if item["id"] == paper_id), None)
        if not paper:
            raise ResearchFlowError(f"{paper_id} is not in {corpus_id}.")
        request = {
            "corpus_id": corpus_id, "paper_id": paper_id,
            "paper_fingerprint": paper["source_fingerprint"],
            "extractor": {"kind": "agent", "name": "DRAFT", "version": "record-runtime-version"},
            "tuples": [{
                "subject": {"type": "Method", "key": "draft/method"},
                "relation": "limited_by",
                "object": {"type": "Limitation", "key": "draft/limitation"},
                "evidence": {
                    "paper_claim_ids": ["C01"],
                    "locators": [{"kind": "page", "value": "1"}],
                    "exact_text_sha256": "0" * 64,
                },
                "epistemic_status": "paper_reported",
            }],
        }
        target = output.expanduser().resolve()
        atomic_text(target, __import__("yaml").safe_dump(request, sort_keys=False, allow_unicode=True))
        return target

    def summary(self) -> dict[str, Any]:
        corpora = self.list()
        return {
            "corpora": len(corpora),
            "valid": sum(1 for item in corpora if self.verify(item["id"])["valid"]),
            "complete_and_reviewed": sum(1 for item in corpora if self.extraction_status(item["id"])["complete_and_reviewed"]),
        }


class GapStore:
    def __init__(self, project):
        self.project = project
        self.folder = project.root / "memory" / "gaps"
        self.run_root = project.root / ".research" / "corpus-gap" / "runs"
        self.corpora = CorpusStore(project)

    def list(self, state: str | None = None) -> list[dict[str, Any]]:
        result = []
        for path in sorted(self.folder.glob("GAP-*.md")):
            record, _ = read_markdown_record(path)
            validate_record("gap", record)
            result.append(record)
        return [item for item in result if state is None or item["state"] == state]

    def show(self, gap_id: str) -> dict[str, Any]:
        path = self.folder / f"{gap_id}.md"
        record, body = read_markdown_record(path)
        validate_record("gap", record)
        if record["id"] != gap_id:
            raise ResearchFlowError(f"Gap ID does not match path: {gap_id}")
        current = gap_fingerprint(record)
        body_current = body.strip() == self._body(record).strip()
        content_current = current == record["candidate_fingerprint"] and body_current
        review_current = record["review"]["reviewed_fingerprint"] in {None, current}
        return {
            "record": record, "body": body, "fingerprint": current,
            "content_current": content_current, "body_current": body_current,
            "review_current": review_current,
            "approved": record["state"] == "approved" and record["review"]["status"] == "approved" and review_current and content_current,
        }

    @staticmethod
    def _matches(item: dict[str, Any], predicate: dict[str, Any]) -> bool:
        mapping = {
            "subject_type": item["subject"]["type"], "relation": item["relation"],
            "object_type": item["object"]["type"], "subject_key": item["subject"]["key"],
            "object_key": item["object"]["key"],
        }
        return all(mapping[key] == value for key, value in predicate.items())

    def _accepted_tuples(self, corpus_id: str) -> tuple[list[dict[str, Any]], list[str]]:
        status = self.corpora.extraction_status(corpus_id)
        if not status["complete_and_reviewed"]:
            pending = [item["paper_id"] for item in status["extractions"] if not item.get("accepted")]
            raise ResearchFlowError("Gap detection requires current accepted extraction for every Corpus paper: " + ", ".join(pending))
        tuples = []
        fingerprints = []
        for item in status["extractions"]:
            record = read_yaml(self.corpora.extraction_root / corpus_id / f"{item['paper_id']}.yaml")
            fingerprints.append(record["extraction_fingerprint"])
            tuples.extend({**value, "paper_id": item["paper_id"]} for value in record["tuples"])
        return sorted(tuples, key=lambda item: item["id"]), sorted(fingerprints)

    def _candidate_for_rule(
        self, corpus: dict[str, Any], rule: dict[str, Any], version: str, tuples: list[dict[str, Any]], run_id: str,
    ) -> dict[str, Any] | None:
        matched = [item for item in tuples if self._matches(item, rule["tuple_match"])]
        if not matched:
            return None
        if rule["motif"] == "missing_edge":
            if "absence_match" not in rule:
                raise ResearchFlowError(f"missing_edge rule {rule['id']} requires absence_match.")
            if any(self._matches(item, rule["absence_match"]) for item in tuples):
                return None
        if rule["motif"] == "contradictory_results":
            if "contradiction_match" not in rule:
                raise ResearchFlowError(f"contradictory_results rule {rule['id']} requires contradiction_match.")
            contrad = [item for item in tuples if self._matches(item, rule["contradiction_match"])]
            if not contrad:
                return None
            matched.extend(contrad)
        from .evidence_graph import RecordResolver
        problem = RecordResolver(self.project).resolve(rule["problem_id"])
        if problem["kind"] != "PROB":
            raise ResearchFlowError(f"Gap rule problem is not a Problem: {rule['problem_id']}")
        corpus_papers = {item["id"] for item in corpus["papers"]}
        for counter in rule.get("known_counterevidence", []):
            if counter["ref"] not in corpus_papers:
                raise ResearchFlowError(f"Gap counterevidence {counter['ref']} is outside the frozen Corpus.")
        derivation = {
            "corpus_id": corpus["id"], "corpus_fingerprint": corpus["corpus_fingerprint"],
            "cgap_run_id": run_id, "motif_id": rule["id"], "motif_version": version,
            "tuple_ids": sorted({item["id"] for item in matched}),
        }
        candidate = {
            "title": rule["title"], "problem_id": rule["problem_id"], "statement": rule["statement"],
            "mechanism_missing": rule["mechanism_missing"], "remaining_scope": rule["remaining_scope"],
            "boundary_conditions": rule["boundary_conditions"],
            "known_counterevidence": rule.get("known_counterevidence", []),
            "falsification": rule["falsification"], "derivation": derivation,
            "scores": rule["scores"], "supersedes": None,
        }
        candidate["candidate_fingerprint"] = gap_fingerprint(candidate)
        return candidate

    def detect(
        self, corpus_id: str, motifs_file: Path, *, dry_run: bool = False, test_only: bool = False
    ) -> dict[str, Any]:
        corpus_result = self.corpora.show(corpus_id)
        if not corpus_result["verification"]["valid"]:
            raise ResearchFlowError("Cannot detect Gaps from an invalid/stale Corpus: " + "; ".join(corpus_result["verification"]["issues"]))
        corpus = corpus_result["record"]
        rules = read_yaml(motifs_file.expanduser().resolve())
        validate_record("motif_rules", rules)
        if len({item["id"] for item in rules["rules"]}) != len(rules["rules"]):
            raise ResearchFlowError("Motif rule IDs must be unique.")
        tuples, extraction_fingerprints = self._accepted_tuples(corpus_id)
        input_fingerprint = canonical_hash({
            "corpus": corpus["corpus_fingerprint"], "extractions": extraction_fingerprints,
            "motifs": rules, "test_only": test_only,
        })
        for manifest_path in sorted(self.run_root.glob("CGAPRUN-*/manifest.yaml")):
            manifest = read_yaml(manifest_path)
            if manifest.get("input_fingerprint") == input_fingerprint:
                return {**manifest, "created": False, "idempotent": True, "dry_run": dry_run}
        preview_run = "CGAPRUN-000000"
        preview = [
            candidate for rule in rules["rules"]
            if (candidate := self._candidate_for_rule(corpus, rule, rules["version"], tuples, preview_run)) is not None
        ]
        if dry_run:
            return {
                "corpus_id": corpus_id, "input_fingerprint": input_fingerprint,
                "candidate_count": len(preview),
                "candidate_fingerprints": [item["candidate_fingerprint"] for item in preview],
                "created": False, "idempotent": False, "dry_run": True,
            }
        with exclusive_lock(self.project.root / ".locks/corpus-gap-detect.lock"):
            for manifest_path in sorted(self.run_root.glob("CGAPRUN-*/manifest.yaml")):
                manifest = read_yaml(manifest_path)
                if manifest.get("input_fingerprint") == input_fingerprint:
                    return {**manifest, "created": False, "idempotent": True, "dry_run": False}
            current_tuples, current_extraction_fingerprints = self._accepted_tuples(corpus_id)
            current_input = canonical_hash({
                "corpus": corpus["corpus_fingerprint"], "extractions": current_extraction_fingerprints,
                "motifs": rules, "test_only": test_only,
            })
            if current_input != input_fingerprint:
                raise ResearchFlowError("Corpus extraction inputs changed during Gap detection; rerun the command.")
            tuples = current_tuples
            run_id = allocate_id(research_home(), "CGAPRUN")
            candidates = [
                candidate for rule in rules["rules"]
                if (candidate := self._candidate_for_rule(corpus, rule, rules["version"], tuples, run_id)) is not None
            ]
            existing = {item["candidate_fingerprint"]: item for item in self.list()}
            run_folder = self.run_root / run_id
            created_paths: list[Path] = []
            try:
                created_gaps = []
                for candidate in candidates:
                    if candidate["candidate_fingerprint"] in existing:
                        created_gaps.append(existing[candidate["candidate_fingerprint"]]["id"])
                        continue
                    gap_id = allocate_id(research_home(), "GAP")
                    record = {
                        "schema_version": 1, "id": gap_id, **candidate,
                        "review": {"status": "pending", "reviewer": None, "reviewed_fingerprint": None, "rationale": None, "reviewed_at": None},
                        "reviews": [], "state": "candidate", "created_at": utc_now(),
                    }
                    validate_record("gap", record)
                    gap_path = self.folder / f"{gap_id}.md"
                    atomic_text(gap_path, markdown_record(record, self._body(record)))
                    created_paths.append(gap_path)
                    created_gaps.append(gap_id)
                manifest = {
                    "schema_version": 1, "id": run_id, "corpus_id": corpus_id,
                    "corpus_fingerprint": corpus["corpus_fingerprint"], "motif_version": rules["version"],
                    "input_fingerprint": input_fingerprint, "candidate_gaps": created_gaps,
                    "created_at": utc_now(), "test_only": test_only,
                }
                validate_record("corpus_gap_run", manifest)
                write_yaml(run_folder / "manifest.yaml", manifest)
                created_paths.append(run_folder / "manifest.yaml")
                atomic_text(run_folder / "motifs.jsonl", "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in rules["rules"]))
                created_paths.append(run_folder / "motifs.jsonl")
                atomic_text(run_folder / "candidates.jsonl", "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in candidates))
                created_paths.append(run_folder / "candidates.jsonl")
                atomic_text(run_folder / "audit.jsonl", json.dumps({
                    "event": "deterministic_gap_detection", "input_fingerprint": input_fingerprint,
                    "rules": len(rules["rules"]), "tuples": len(tuples), "candidates": len(candidates),
                    "test_only": test_only,
                    "meaning": "Heuristic candidates require human review and do not establish an open research gap.",
                }, ensure_ascii=False, sort_keys=True) + "\n")
                created_paths.append(run_folder / "audit.jsonl")
                return {**manifest, "created": True, "idempotent": False, "dry_run": False}
            except Exception:
                for created_path in reversed(created_paths):
                    created_path.unlink(missing_ok=True)
                if run_folder.exists():
                    try:
                        run_folder.rmdir()
                    except OSError:
                        pass
                raise

    def review(
        self, gap_id: str, *, decision: str, reviewer: str, rationale: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if decision not in {"approve", "reject"}:
            raise ResearchFlowError("Gap review decision must be approve or reject.")
        if not reviewer.startswith("human:") or not reviewer.removeprefix("human:").strip():
            raise ResearchFlowError("Only a human:* reviewer may approve or reject a Gap.")
        if not rationale.strip():
            raise ResearchFlowError("Gap review requires a non-empty rationale.")
        status = "approved" if decision == "approve" else "rejected"
        def prepare() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
            shown = self.show(gap_id)
            if not shown["content_current"]:
                raise ResearchFlowError("Gap content fingerprint is stale; review cannot be applied.")
            review = {
                "status": status, "reviewer": reviewer, "reviewed_fingerprint": shown["fingerprint"],
                "rationale": rationale.strip(), "reviewed_at": utc_now(),
            }
            record = shown["record"]
            candidate = {**record, "review": review, "reviews": [*record["reviews"], review], "state": status}
            validate_record("gap", candidate)
            return shown, review, candidate

        if dry_run:
            _, review, _ = prepare()
        else:
            with exclusive_lock(self.project.root / ".locks/gap-review.lock"):
                shown, review, candidate = prepare()
                atomic_text(self.folder / f"{gap_id}.md", markdown_record(candidate, shown["body"]))
        return {"gap_id": gap_id, "state": status, "review": review, "dry_run": dry_run}

    @staticmethod
    def _body(record: dict[str, Any]) -> str:
        boundaries = "\n".join(f"- {item}" for item in record["boundary_conditions"])
        counters = "\n".join(
            f"- {item['ref']}: {item['effect']} — {item['rationale']}"
            for item in record["known_counterevidence"]
        ) or "- None recorded."
        return (
            f"# {record['title']}\n\n## Candidate Gap\n\n{record['statement']}\n\n"
            f"## Missing Mechanism\n\n{record['mechanism_missing']}\n\n"
            f"## Remaining Scope\n\n{record['remaining_scope']}\n\n"
            f"## Boundary Conditions\n\n{boundaries}\n\n## Counterevidence\n\n{counters}\n\n"
            f"## Falsification\n\n{record['falsification']}\n\n"
            "## Epistemic Boundary\n\nThis is a deterministic heuristic candidate. Human approval permits hypothesis formation but does not prove that the Gap is open."
        )

    def summary(self) -> dict[str, Any]:
        values = self.list()
        return {
            "gaps": len(values),
            "candidate": sum(item["state"] == "candidate" for item in values),
            "approved": sum(item["state"] == "approved" for item in values),
            "rejected": sum(item["state"] == "rejected" for item in values),
        }
