from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import research_home
from .corpus_gap import canonical_hash
from .errors import ResearchFlowError
from .ids import allocate_id
from .io import exclusive_lock, read_yaml, utc_now, write_yaml
from .schema import validate_record


CONCEPT_RELATIVE_PATH = Path(".research/paper-adjacency/concepts.yaml")
CONCEPT_LOCK_PATH = Path(".locks/paper-concepts-write.lock")


def concept_fingerprint(value: dict[str, Any]) -> str:
    return canonical_hash({
        key: value[key]
        for key in (
            "type", "canonical_key", "label", "aliases", "broader_key",
            "related_keys", "rationale", "source",
        )
    })


class ConceptStore:
    """Human-reviewed project vocabulary used to normalize extraction nodes."""

    def __init__(self, project):
        self.project = project
        self.path = project.root / CONCEPT_RELATIVE_PATH
        self._resolve_index: dict[tuple[str, str], dict[str, Any]] | None = None

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "schema_version": 1,
            "vocabulary_id": "project-paper-concepts",
            "concepts": [],
            "updated_at": utc_now(),
        }

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        record = read_yaml(self.path)
        validate_record("concept_vocabulary", record)
        self._validate_integrity(record)
        return record

    def _validate_integrity(self, record: dict[str, Any]) -> None:
        ids: set[str] = set()
        occupied: dict[tuple[str, str], str] = {}
        concepts = record["concepts"]
        for item in concepts:
            if item["id"] in ids:
                raise ResearchFlowError(f"Duplicate concept ID: {item['id']}")
            ids.add(item["id"])
            if concept_fingerprint(item) != item["concept_fingerprint"]:
                raise ResearchFlowError(f"Concept content fingerprint changed: {item['id']}")
            if item["canonical_key"] in item["aliases"]:
                raise ResearchFlowError(f"Concept alias repeats its canonical key: {item['id']}")
            for key in (item["canonical_key"], *item["aliases"]):
                marker = (item["type"], key)
                if marker in occupied:
                    raise ResearchFlowError(
                        f"Concept key {item['type']}:{key} is ambiguous between "
                        f"{occupied[marker]} and {item['id']}."
                    )
                occupied[marker] = item["id"]
            review = item["review"]
            if item["status"] == "accepted" and review["reviewed_fingerprint"] != item["concept_fingerprint"]:
                raise ResearchFlowError(f"Accepted concept review is stale: {item['id']}")

        accepted = {
            (item["type"], item["canonical_key"]): item
            for item in concepts if item["status"] == "accepted"
        }
        for item in accepted.values():
            broader = item["broader_key"]
            if broader and (item["type"], broader) not in accepted:
                raise ResearchFlowError(
                    f"Accepted concept {item['id']} has unavailable accepted broader key: {broader}"
                )
            for related in item["related_keys"]:
                if (item["type"], related) not in accepted:
                    raise ResearchFlowError(
                        f"Accepted concept {item['id']} has unavailable accepted related key: {related}"
                    )
        for marker in accepted:
            seen: set[tuple[str, str]] = set()
            current = marker
            while current in accepted and accepted[current]["broader_key"]:
                if current in seen:
                    raise ResearchFlowError(f"Concept broader hierarchy has a cycle at {current[0]}:{current[1]}")
                seen.add(current)
                current = (current[0], accepted[current]["broader_key"])

    def _write(self, record: dict[str, Any]) -> None:
        candidate = {**record, "updated_at": utc_now()}
        validate_record("concept_vocabulary", candidate)
        self._validate_integrity(candidate)
        write_yaml(self.path, candidate)
        self._resolve_index = None

    def _normalize_request(self, request_file: Path) -> dict[str, Any]:
        request = read_yaml(request_file.expanduser().resolve())
        validate_record("concept_request", request)
        normalized = dict(request)
        normalized["aliases"] = sorted(set(request["aliases"]))
        normalized["related_keys"] = sorted(set(request["related_keys"]))
        if normalized["broader_key"] == normalized["canonical_key"]:
            raise ResearchFlowError("A concept cannot be broader than itself.")
        if normalized["canonical_key"] in normalized["related_keys"]:
            raise ResearchFlowError("A concept cannot be related to itself.")
        normalized["concept_fingerprint"] = concept_fingerprint(normalized)
        ledger = self.load()
        for item in ledger["concepts"]:
            if item["type"] != normalized["type"]:
                continue
            overlap = {item["canonical_key"], *item["aliases"]} & {
                normalized["canonical_key"], *normalized["aliases"]
            }
            if overlap:
                if item["concept_fingerprint"] == normalized["concept_fingerprint"]:
                    normalized["existing"] = item
                    return normalized
                raise ResearchFlowError(
                    f"Concept key already belongs to {item['id']}: {', '.join(sorted(overlap))}"
                )
        return normalized

    def preflight(self, request_file: Path) -> dict[str, Any]:
        normalized = self._normalize_request(request_file)
        return {
            "valid": True,
            "concept_fingerprint": normalized["concept_fingerprint"],
            "idempotent_existing_id": normalized.get("existing", {}).get("id"),
            "meaning": "Concept syntax and key uniqueness pass; normalization remains review-pending.",
        }

    def add_file(self, request_file: Path, *, dry_run: bool = False) -> dict[str, Any]:
        normalized = self._normalize_request(request_file)
        existing = normalized.pop("existing", None)
        if existing:
            return {"concept": existing, "created": False, "idempotent": True, "dry_run": dry_run}
        if dry_run:
            return {"created": False, "idempotent": False, "dry_run": True, **normalized}
        with exclusive_lock(self.project.root / CONCEPT_LOCK_PATH):
            normalized = self._normalize_request(request_file)
            existing = normalized.pop("existing", None)
            if existing:
                return {"concept": existing, "created": False, "idempotent": True, "dry_run": False}
            ledger = self.load()
            concept = {
                "id": allocate_id(research_home(), "CONCEPT"), **normalized,
                "status": "candidate",
                "review": {
                    "status": "pending", "reviewer": None, "reviewed_fingerprint": None,
                    "rationale": None, "reviewed_at": None,
                },
                "reviews": [], "created_at": utc_now(),
            }
            self._write({**ledger, "concepts": [*ledger["concepts"], concept]})
            return {"concept": concept, "created": True, "idempotent": False, "dry_run": False}

    def list(self, *, status: str | None = None, node_type: str | None = None) -> list[dict[str, Any]]:
        values = self.load()["concepts"]
        return [
            item for item in values
            if (status is None or item["status"] == status)
            and (node_type is None or item["type"] == node_type)
        ]

    def show(self, concept_id: str) -> dict[str, Any]:
        item = next((value for value in self.load()["concepts"] if value["id"] == concept_id), None)
        if not item:
            raise ResearchFlowError(f"Concept not found: {concept_id}")
        return {"concept": item, "current": concept_fingerprint(item) == item["concept_fingerprint"]}

    def review(
        self, concept_id: str, *, decision: str, reviewer: str, rationale: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if decision not in {"accepted", "revision_requested", "rejected"}:
            raise ResearchFlowError("Concept decision must be accepted, revision_requested, or rejected.")
        if decision == "accepted" and (
            not reviewer.startswith("human:") or not reviewer.removeprefix("human:").strip()
        ):
            raise ResearchFlowError("Only a human:* reviewer may accept a concept normalization.")
        if not reviewer.strip() or not rationale.strip():
            raise ResearchFlowError("Concept review needs a reviewer and rationale.")

        def prepare(ledger: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            index = next((i for i, item in enumerate(ledger["concepts"]) if item["id"] == concept_id), None)
            if index is None:
                raise ResearchFlowError(f"Concept not found: {concept_id}")
            item = ledger["concepts"][index]
            if concept_fingerprint(item) != item["concept_fingerprint"]:
                raise ResearchFlowError("Cannot review changed concept content.")
            review = {
                "status": decision, "reviewer": reviewer.strip(),
                "reviewed_fingerprint": item["concept_fingerprint"],
                "rationale": rationale.strip(), "reviewed_at": utc_now(),
            }
            updated = {**item, "status": decision, "review": review, "reviews": [*item["reviews"], review]}
            concepts = list(ledger["concepts"])
            concepts[index] = updated
            candidate = {**ledger, "concepts": concepts}
            if decision == "accepted":
                self._validate_integrity({**candidate, "updated_at": ledger["updated_at"]})
            return review, candidate

        if dry_run:
            review, _ = prepare(self.load())
        else:
            with exclusive_lock(self.project.root / CONCEPT_LOCK_PATH):
                review, candidate = prepare(self.load())
                self._write(candidate)
        return {"id": concept_id, "review": review, "dry_run": dry_run}

    def resolve(self, node_type: str, key: str) -> dict[str, Any]:
        if self._resolve_index is None:
            accepted = [item for item in self.load()["concepts"] if item["status"] == "accepted"]
            self._resolve_index = {
                (item["type"], alias): item
                for item in accepted
                for alias in (item["canonical_key"], *item["aliases"])
            }
        match = self._resolve_index.get((node_type, key))
        if not match:
            return {
                "type": node_type, "input_key": key, "canonical_key": key,
                "broader_keys": [], "related_keys": [], "known": False,
            }
        accepted = [item for item in self._resolve_index.values()]
        by_key = {(item["type"], item["canonical_key"]): item for item in accepted}
        broader = []
        current = match
        while current["broader_key"]:
            broader.append(current["broader_key"])
            current = by_key[(node_type, current["broader_key"])]
        return {
            "type": node_type, "input_key": key, "canonical_key": match["canonical_key"],
            "broader_keys": broader, "related_keys": match["related_keys"],
            "known": True, "concept_id": match["id"],
        }

    def fingerprint(self) -> str:
        accepted = [
            item["concept_fingerprint"] for item in self.load()["concepts"]
            if item["status"] == "accepted"
        ]
        return canonical_hash(sorted(accepted))

    def check(self) -> dict[str, Any]:
        ledger = self.load()
        accepted = sum(1 for item in ledger["concepts"] if item["status"] == "accepted")
        return {
            "initialized": self.path.exists(), "valid": True, "issues": [],
            "concepts": len(ledger["concepts"]), "accepted": accepted,
            "fingerprint": self.fingerprint(),
            "meaning": "Accepted concepts normalize names; they do not establish paper relationships.",
        }
