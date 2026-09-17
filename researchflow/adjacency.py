from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .config import research_home
from .corpus_gap import CorpusStore, _safe_workspace_path, canonical_hash
from .errors import ResearchFlowError
from .ids import allocate_id
from .io import atomic_text, exclusive_lock, read_yaml, utc_now, write_yaml
from .schema import validate_record


ADJACENCY_RELATIVE_PATH = Path(".research/paper-adjacency/edges.yaml")
LOCK_RELATIVE_PATH = Path(".locks/paper-adjacency-write.lock")
GENERATOR_VERSION = "structural-v1.1"
SEMANTIC_GENERATOR_VERSION = "semantic-v2.1"

RELATIONS = {
    "same_problem", "same_method_family", "extends_method", "replaces_component",
    "shares_assumption", "relaxes_assumption", "same_evaluation",
    "contradicts_result", "addresses_limitation", "exposes_failure",
    "counterevidence", "boundary_case",
}
SYMMETRIC_RELATIONS = {"same_problem", "same_method_family", "shares_assumption", "same_evaluation"}
METHOD_ADOPTION_ROLES = {
    ("object", "proposes"),
    ("subject", "uses_component"),
    ("subject", "trained_with"),
    ("subject", "uses_feedback"),
    ("subject", "evaluated_on"),
    ("subject", "uses_dataset"),
    ("subject", "reports_result"),
    ("subject", "assumes"),
    ("subject", "requires"),
    ("subject", "limited_by"),
    ("subject", "fails_under"),
    ("subject", "generalizes_to"),
}


def adjacency_fingerprint(edge: dict[str, Any]) -> str:
    stable = {
        key: edge[key]
        for key in (
            "corpus_id", "from", "relation", "to", "directed", "dimensions",
            "evidence", "rationale", "score", "generator", "source_fingerprints",
        )
    }
    if edge.get("semantic_context"):
        stable["semantic_context"] = edge["semantic_context"]
    return canonical_hash(stable)


class PaperAdjacencyStore:
    """Evidence-bound PAPER-to-PAPER relationships derived from an accepted Corpus."""

    def __init__(self, project):
        self.project = project
        self.path = project.root / ADJACENCY_RELATIVE_PATH
        self.corpora = CorpusStore(project)

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "schema_version": 1,
            "adjacency_id": "project-paper-adjacency",
            "builds": [],
            "edges": [],
            "updated_at": utc_now(),
        }

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        record = read_yaml(self.path)
        validate_record("paper_adjacency", record)
        ids = [item["id"] for item in record["edges"]]
        if len(ids) != len(set(ids)):
            raise ResearchFlowError("PaperAdjacency contains duplicate edge IDs.")
        for edge in record["edges"]:
            fingerprint = edge["generator"].get("input_fingerprint", "")
            if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
                raise ResearchFlowError(
                    f"PaperAdjacency {edge['id']} is missing a valid generator input fingerprint."
                )
        return record

    def _write(self, record: dict[str, Any]) -> None:
        candidate = {**record, "updated_at": utc_now()}
        validate_record("paper_adjacency", candidate)
        write_yaml(self.path, candidate)

    def _corpus_inputs(self, corpus_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
        shown = self.corpora.show(corpus_id)
        if not shown["verification"]["valid"]:
            raise ResearchFlowError("Paper adjacency requires a valid current Corpus: " + "; ".join(shown["verification"]["issues"]))
        status = self.corpora.extraction_status(corpus_id)
        if not status["complete_and_reviewed"]:
            missing = [item["paper_id"] for item in status["extractions"] if not item.get("accepted")]
            raise ResearchFlowError(
                "Paper adjacency requires current human-accepted extraction for every Corpus paper: "
                + ", ".join(missing)
            )
        tuples: list[dict[str, Any]] = []
        extraction_fingerprints: list[str] = []
        for item in status["extractions"]:
            record = read_yaml(self.corpora.extraction_root / corpus_id / f"{item['paper_id']}.yaml")
            extraction_fingerprints.append(record["extraction_fingerprint"])
            tuples.extend({
                **value, "paper_id": item["paper_id"],
                "_extraction_schema_version": record.get("schema_version", 1),
            } for value in record["tuples"])
        return shown["record"], sorted(tuples, key=lambda value: value["id"]), sorted(extraction_fingerprints)

    @staticmethod
    def _is_role_occurrence(item: dict[str, Any], endpoint: str) -> bool:
        node = item[endpoint]
        return node["type"] != "Method" or (endpoint, item["relation"]) in METHOD_ADOPTION_ROLES

    @staticmethod
    def _node_occurrences(tuples: list[dict[str, Any]]) -> dict[str, dict[tuple[str, str], list[dict[str, Any]]]]:
        by_paper: dict[str, dict[tuple[str, str], list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for item in tuples:
            for endpoint in ("subject", "object"):
                if not PaperAdjacencyStore._is_role_occurrence(item, endpoint):
                    continue
                node = item[endpoint]
                by_paper[item["paper_id"]][(node["type"], node["key"])].append(item)
        return by_paper

    def _paper_analysis_fingerprints(self, paper_ids: list[str]) -> dict[str, str]:
        result = {}
        for paper_id in paper_ids:
            paper = self.project.evidence.show(paper_id)
            result[paper_id] = canonical_hash({"metadata": paper["metadata"], "body": paper["body"]})
        return result

    @staticmethod
    def _evidence(paper_id: str, tuples: list[dict[str, Any]]) -> dict[str, Any]:
        claims = sorted({claim for item in tuples for claim in item["evidence"]["paper_claim_ids"]})
        locators = []
        seen = set()
        for item in tuples:
            for locator in item["evidence"]["locators"]:
                marker = (locator["kind"], locator["value"])
                if marker not in seen:
                    seen.add(marker)
                    locators.append(locator)
        return {
            "paper_id": paper_id,
            "tuple_ids": sorted({item["id"] for item in tuples}),
            "claim_ids": claims,
            "locators": locators,
        }

    def _candidate(
        self,
        *,
        corpus: dict[str, Any],
        source: str,
        relation: str,
        target: str,
        dimensions: list[str],
        source_tuples: list[dict[str, Any]],
        target_tuples: list[dict[str, Any]],
        rationale: str,
        input_fingerprint: str,
        shared_count: int,
        directed: bool,
        generator_kind: str = "deterministic_structural",
        generator_version: str = GENERATOR_VERSION,
        semantic_score: float | None = None,
        paper_fingerprints: dict[str, str] | None = None,
        vocabulary_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        if relation in SYMMETRIC_RELATIONS and source > target:
            source, target = target, source
            source_tuples, target_tuples = target_tuples, source_tuples
        fingerprints = paper_fingerprints or self._paper_analysis_fingerprints([source, target])
        structural = min(1.0, round(0.5 + 0.1 * max(shared_count - 1, 0), 4))
        overall = semantic_score if semantic_score is not None else structural
        edge = {
            "corpus_id": corpus["id"],
            "from": source,
            "relation": relation,
            "to": target,
            "directed": directed,
            "dimensions": sorted(set(dimensions)),
            "evidence": [self._evidence(source, source_tuples), self._evidence(target, target_tuples)],
            "rationale": rationale,
            "score": {
                "structural": structural,
                "semantic": semantic_score,
                "overall": overall,
                "basis": (
                    f"deterministic accepted ontology/semantic-tuple evidence; {shared_count} matched key(s)"
                    if semantic_score is not None
                    else f"deterministic shared-structure evidence; {shared_count} matched key(s)"
                ),
            },
            "generator": {
                "kind": generator_kind,
                "name": "ResearchFlow PaperAdjacency",
                "version": generator_version,
                "input_fingerprint": input_fingerprint,
            },
            "source_fingerprints": {source: fingerprints[source], target: fingerprints[target]},
        }
        if generator_kind == "deterministic_semantic":
            edge["semantic_context"] = {
                "vocabulary_fingerprint": vocabulary_fingerprint,
                "algorithm": generator_version,
            }
        edge["adjacency_fingerprint"] = adjacency_fingerprint(edge)
        return edge

    def _structural_candidates(
        self, corpus: dict[str, Any], tuples: list[dict[str, Any]], input_fingerprint: str
    ) -> list[dict[str, Any]]:
        occurrences = self._node_occurrences(tuples)
        papers = sorted(occurrences)
        paper_fingerprints = self._paper_analysis_fingerprints(papers)
        candidates: list[dict[str, Any]] = []
        shared_specs = (
            ("Task", "same_problem", ["problem", "task"]),
            ("Method", "same_method_family", ["method"]),
            ("Assumption", "shares_assumption", ["assumption"]),
        )
        for index, source in enumerate(papers):
            for target in papers[index + 1:]:
                for node_type, relation, dimensions in shared_specs:
                    keys = sorted(
                        key for kind, key in set(occurrences[source]) & set(occurrences[target]) if kind == node_type
                    )
                    if not keys:
                        continue
                    source_tuples = [item for key in keys for item in occurrences[source][(node_type, key)]]
                    target_tuples = [item for key in keys for item in occurrences[target][(node_type, key)]]
                    candidates.append(self._candidate(
                        corpus=corpus, source=source, relation=relation, target=target,
                        dimensions=dimensions, source_tuples=source_tuples, target_tuples=target_tuples,
                        rationale=f"Both papers contain the same {node_type} key(s): {', '.join(keys)}.",
                        input_fingerprint=input_fingerprint, shared_count=len(keys), directed=False,
                        paper_fingerprints=paper_fingerprints,
                    ))
                evaluation_matches: list[tuple[str, str]] = []
                for kind, key in set(occurrences[source]) & set(occurrences[target]):
                    if kind in {"Dataset", "Metric"}:
                        evaluation_matches.append((kind, key))
                if evaluation_matches:
                    source_tuples = [item for node in evaluation_matches for item in occurrences[source][node]]
                    target_tuples = [item for node in evaluation_matches for item in occurrences[target][node]]
                    dimensions = sorted({"dataset" if kind == "Dataset" else "metric" for kind, _ in evaluation_matches} | {"evaluation"})
                    labels = ", ".join(f"{kind}:{key}" for kind, key in sorted(evaluation_matches))
                    candidates.append(self._candidate(
                        corpus=corpus, source=source, relation="same_evaluation", target=target,
                        dimensions=dimensions, source_tuples=source_tuples, target_tuples=target_tuples,
                        rationale=f"Both papers use the same evaluation key(s): {labels}.",
                        input_fingerprint=input_fingerprint, shared_count=len(evaluation_matches), directed=False,
                        paper_fingerprints=paper_fingerprints,
                    ))

        # Directional failure evidence: one paper reports a Method failing under a
        # condition and another paper contains that same Method key.
        for source in papers:
            failures = [item for item in tuples if item["paper_id"] == source and item["relation"] == "fails_under" and item["subject"]["type"] == "Method"]
            for failure in failures:
                method = ("Method", failure["subject"]["key"])
                for target in papers:
                    if target == source or method not in occurrences[target]:
                        continue
                    candidates.append(self._candidate(
                        corpus=corpus, source=source, relation="exposes_failure", target=target,
                        dimensions=["method", "failure_condition"], source_tuples=[failure],
                        target_tuples=occurrences[target][method],
                        rationale=f"{source} reports a failure condition for Method:{method[1]}, which is also used by {target}.",
                        input_fingerprint=input_fingerprint, shared_count=1, directed=True,
                        paper_fingerprints=paper_fingerprints,
                    ))

        unique = {item["adjacency_fingerprint"]: item for item in candidates}
        return sorted(unique.values(), key=lambda item: (item["from"], item["relation"], item["to"]))

    def _semantic_candidates(
        self, corpus: dict[str, Any], tuples: list[dict[str, Any]], input_fingerprint: str
    ) -> list[dict[str, Any]]:
        from .concepts import ConceptStore

        concepts = ConceptStore(self.project)
        vocabulary_fingerprint = concepts.fingerprint()

        def normalized(node: dict[str, Any]) -> dict[str, Any]:
            return concepts.resolve(node["type"], node["key"])

        by_paper: dict[str, list[dict[str, Any]]] = defaultdict(list)
        occurrences: dict[str, dict[tuple[str, str], list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        broader: dict[str, dict[tuple[str, str], list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for item in tuples:
            by_paper[item["paper_id"]].append(item)
            for endpoint in ("subject", "object"):
                if not self._is_role_occurrence(item, endpoint):
                    continue
                node = item[endpoint]
                resolved = normalized(node)
                occurrences[item["paper_id"]][(node["type"], resolved["canonical_key"])].append(item)
                for key in resolved["broader_keys"]:
                    broader[item["paper_id"]][(node["type"], key)].append(item)

        papers = sorted(by_paper)
        paper_fingerprints = self._paper_analysis_fingerprints(papers)
        candidates: list[dict[str, Any]] = []
        shared_specs = (
            (("Problem", "Task"), "same_problem", ["problem", "task"]),
            (("Method",), "same_method_family", ["method"]),
            (("Assumption",), "shares_assumption", ["assumption"]),
            (("Dataset", "Metric"), "same_evaluation", ["evaluation"]),
        )
        for index, source in enumerate(papers):
            for target in papers[index + 1:]:
                for node_types, relation, dimensions in shared_specs:
                    exact = sorted(
                        marker for marker in set(occurrences[source]) & set(occurrences[target])
                        if marker[0] in node_types
                    )
                    family = sorted(
                        marker for marker in set(broader[source]) & set(broader[target])
                        if marker[0] in node_types
                    )
                    matches = exact or family
                    if not matches:
                        continue
                    source_tuples = [
                        item for marker in matches
                        for item in (occurrences[source][marker] if exact else broader[source][marker])
                    ]
                    target_tuples = [
                        item for marker in matches
                        for item in (occurrences[target][marker] if exact else broader[target][marker])
                    ]
                    labels = ", ".join(f"{kind}:{key}" for kind, key in matches)
                    basis = "accepted canonical concept" if exact else "accepted broader concept"
                    candidates.append(self._candidate(
                        corpus=corpus, source=source, relation=relation, target=target,
                        dimensions=dimensions, source_tuples=source_tuples, target_tuples=target_tuples,
                        rationale=f"Both papers map to the same {basis}: {labels}.",
                        input_fingerprint=input_fingerprint, shared_count=len(matches), directed=False,
                        generator_kind="deterministic_semantic", generator_version=SEMANTIC_GENERATOR_VERSION,
                        semantic_score=0.75 if exact else 0.65,
                        paper_fingerprints=paper_fingerprints,
                        vocabulary_fingerprint=vocabulary_fingerprint,
                    ))

        target_relations = {
            "extends": ("extends_method", "Method", "proposes", ["method"]),
            "replaces": ("replaces_component", None, "uses_component", ["component", "method"]),
            "addresses": ("addresses_limitation", "Limitation", "limited_by", ["limitation"]),
            "contradicts": ("contradicts_result", "Result", "reports_result", ["result"]),
        }
        for source in papers:
            for source_tuple in by_paper[source]:
                if source_tuple["relation"] not in target_relations:
                    continue
                relation, expected_type, target_relation, dimensions = target_relations[source_tuple["relation"]]
                node = source_tuple["object"]
                if expected_type and node["type"] != expected_type:
                    continue
                resolved = normalized(node)
                keys = {resolved["canonical_key"], *resolved["broader_keys"]}
                for target in papers:
                    if target == source:
                        continue
                    matched = []
                    for target_tuple in by_paper[target]:
                        if target_tuple["relation"] != target_relation:
                            continue
                        target_node = target_tuple["object"]
                        if expected_type and target_node["type"] != expected_type:
                            continue
                        target_resolved = normalized(target_node)
                        target_keys = {target_resolved["canonical_key"], *target_resolved["broader_keys"]}
                        if keys & target_keys:
                            matched.append(target_tuple)
                    if matched:
                        candidates.append(self._candidate(
                            corpus=corpus, source=source, relation=relation, target=target,
                            dimensions=dimensions, source_tuples=[source_tuple], target_tuples=matched,
                            rationale=(
                                f"{source} explicitly reports `{source_tuple['relation']}` for "
                                f"{node['type']}:{node['key']}, matching evidence in {target}."
                            ),
                            input_fingerprint=input_fingerprint, shared_count=len(matched), directed=True,
                            generator_kind="deterministic_semantic", generator_version=SEMANTIC_GENERATOR_VERSION,
                            semantic_score=0.85,
                            paper_fingerprints=paper_fingerprints,
                            vocabulary_fingerprint=vocabulary_fingerprint,
                        ))

        # A failure transfers directly to the same adopted canonical Method.
        # A broader family match is only a candidate when the papers also share
        # a FailureCondition, Task, or Assumption; family membership alone is
        # not evidence that a concrete failure applies to another method.
        for source in papers:
            for failure in (item for item in by_paper[source] if item["relation"] == "fails_under"):
                method = normalized(failure["subject"])
                for target in papers:
                    if target == source:
                        continue
                    exact_marker = ("Method", method["canonical_key"])
                    matched = list(occurrences[target].get(exact_marker, []))
                    context: list[tuple[str, str]] = []
                    match_basis = "same canonical method"
                    if not matched:
                        family_keys = set(method["broader_keys"])
                        family_markers = [("Method", key) for key in sorted(family_keys)]
                        matched = [item for marker in family_markers for item in broader[target].get(marker, [])]
                        context = sorted(
                            marker for marker in set(occurrences[source]) & set(occurrences[target])
                            if marker[0] in {"FailureCondition", "Task", "Assumption"}
                        )
                        if not matched or not context:
                            continue
                        match_basis = "shared broader method family plus " + ", ".join(
                            f"{kind}:{key}" for kind, key in context
                        )
                    if matched:
                        candidates.append(self._candidate(
                            corpus=corpus, source=source, relation="exposes_failure", target=target,
                            dimensions=["method", "failure_condition"], source_tuples=[failure],
                            target_tuples=matched,
                            rationale=f"{source} reports a failure condition linked to {target} by {match_basis}.",
                            input_fingerprint=input_fingerprint, shared_count=1, directed=True,
                            generator_kind="deterministic_semantic", generator_version=SEMANTIC_GENERATOR_VERSION,
                            semantic_score=0.8 if not context else 0.7,
                            paper_fingerprints=paper_fingerprints,
                            vocabulary_fingerprint=vocabulary_fingerprint,
                        ))

        # One candidate per semantic triple; merge evidence produced through
        # multiple matching concepts without hiding the deterministic rationale.
        unique: dict[tuple[str, str, str], dict[str, Any]] = {}
        for item in candidates:
            marker = (item["from"], item["relation"], item["to"])
            if marker not in unique or item["score"]["overall"] > unique[marker]["score"]["overall"]:
                unique[marker] = item
        return sorted(unique.values(), key=lambda item: (item["from"], item["relation"], item["to"]))

    def _build_inputs(self, corpus_id: str, mode: str) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        corpus, tuples, extraction_fingerprints = self._corpus_inputs(corpus_id)
        if mode not in {"structural", "semantic"}:
            raise ResearchFlowError("Adjacency build mode must be structural or semantic.")
        from .concepts import ConceptStore
        vocabulary_fingerprint = ConceptStore(self.project).fingerprint() if mode == "semantic" else None
        generator = SEMANTIC_GENERATOR_VERSION if mode == "semantic" else GENERATOR_VERSION
        input_fingerprint = canonical_hash({
            "corpus": corpus["corpus_fingerprint"],
            "extractions": extraction_fingerprints,
            "vocabulary": vocabulary_fingerprint,
            "generator": generator,
        })
        return corpus, tuples, input_fingerprint

    def preview(self, corpus_id: str, *, mode: str = "structural") -> dict[str, Any]:
        corpus, tuples, input_fingerprint = self._build_inputs(corpus_id, mode)
        candidates = (
            self._semantic_candidates(corpus, tuples, input_fingerprint)
            if mode == "semantic"
            else self._structural_candidates(corpus, tuples, input_fingerprint)
        )
        return {
            "corpus_id": corpus_id, "mode": mode, "input_fingerprint": input_fingerprint,
            "candidate_count": len(candidates), "relations": self._relation_counts(candidates),
            "candidates": candidates,
        }

    def build(
        self, corpus_id: str, *, mode: str = "structural", details: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        corpus, _, input_fingerprint = self._build_inputs(corpus_id, mode)
        ledger = self.load()
        existing_build = next((item for item in ledger["builds"] if item["input_fingerprint"] == input_fingerprint), None)
        if existing_build:
            result = {
                **existing_build, "mode": mode, "candidate_count": len(existing_build["edge_ids"]),
                "created": False, "idempotent": True, "dry_run": dry_run,
            }
            if details:
                preview = self.preview(corpus_id, mode=mode)
                result["candidates"] = [self._candidate_summary(item) for item in preview["candidates"]]
            return result
        preview = self.preview(corpus_id, mode=mode)
        candidates = preview["candidates"]
        if dry_run:
            result = {
                "corpus_id": corpus_id, "input_fingerprint": input_fingerprint,
                "mode": mode,
                "candidate_count": len(candidates),
                "relations": self._relation_counts(candidates),
                "created": False, "idempotent": False, "dry_run": True,
            }
            if details:
                result["candidates"] = [self._candidate_summary(item) for item in candidates]
            return result
        with exclusive_lock(self.project.root / LOCK_RELATIVE_PATH):
            ledger = self.load()
            existing_build = next((item for item in ledger["builds"] if item["input_fingerprint"] == input_fingerprint), None)
            if existing_build:
                result = {
                    **existing_build, "mode": mode, "candidate_count": len(existing_build["edge_ids"]),
                    "created": False, "idempotent": True, "dry_run": False,
                }
                if details:
                    preview = self.preview(corpus_id, mode=mode)
                    result["candidates"] = [self._candidate_summary(item) for item in preview["candidates"]]
                return result
            existing_fingerprints = {item["adjacency_fingerprint"]: item for item in ledger["edges"]}
            edge_ids: list[str] = []
            added = []
            for candidate in candidates:
                if candidate["adjacency_fingerprint"] in existing_fingerprints:
                    edge_ids.append(existing_fingerprints[candidate["adjacency_fingerprint"]]["id"])
                    continue
                edge = {
                    "id": allocate_id(research_home(), "PADJ"),
                    **candidate,
                    "status": "candidate",
                    "review": {"status": "pending", "reviewer": None, "reviewed_fingerprint": None, "rationale": None, "reviewed_at": None},
                    "reviews": [],
                    "created_at": utc_now(),
                }
                edge_ids.append(edge["id"])
                added.append(edge)
            build = {
                "corpus_id": corpus_id,
                "corpus_fingerprint": corpus["corpus_fingerprint"],
                "generator_version": SEMANTIC_GENERATOR_VERSION if mode == "semantic" else GENERATOR_VERSION,
                "input_fingerprint": input_fingerprint,
                "edge_ids": edge_ids,
                "created_at": utc_now(),
            }
            self._write({**ledger, "edges": [*ledger["edges"], *added], "builds": [*ledger["builds"], build]})
            return {**build, "candidate_count": len(candidates), "created_edges": len(added), "created": True, "idempotent": False, "dry_run": False}

    @staticmethod
    def _candidate_summary(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "from": item["from"], "relation": item["relation"], "to": item["to"],
            "dimensions": item["dimensions"], "score": item["score"],
            "rationale": item["rationale"],
            "evidence": [
                {
                    "paper_id": value["paper_id"], "tuple_ids": value["tuple_ids"],
                    "claim_ids": value["claim_ids"], "locators": value["locators"],
                }
                for value in item["evidence"]
            ],
        }

    @staticmethod
    def _key_tokens(key: str) -> set[str]:
        ignored = {
            "a", "an", "and", "for", "in", "of", "on", "the", "to", "with",
            "paper", "method", "task", "problem", "navigation", "assumption",
            "limitation", "result", "component", "dataset", "metric",
        }
        return {
            part for part in re.split(r"[./_-]+", key.casefold())
            if len(part) > 1 and part not in ignored
        }

    def packet(self, corpus_id: str, *, top_k: int = 25) -> dict[str, Any]:
        if top_k < 1:
            raise ResearchFlowError("--top-k must be positive.")
        corpus, tuples, input_fingerprint = self._build_inputs(corpus_id, "semantic")
        from .concepts import ConceptStore
        concepts = ConceptStore(self.project)
        by_paper: dict[str, list[dict[str, Any]]] = defaultdict(list)
        profiles: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for item in tuples:
            by_paper[item["paper_id"]].append(item)
            for endpoint in ("subject", "object"):
                if not self._is_role_occurrence(item, endpoint):
                    continue
                node = item[endpoint]
                resolved = concepts.resolve(node["type"], node["key"])
                profiles[item["paper_id"]][node["type"]].add(resolved["canonical_key"])
                profiles[item["paper_id"]][node["type"]].update(resolved["broader_keys"])

        weights = {
            "Problem": 1.0, "Task": 1.0, "Method": 1.0, "Component": 0.9,
            "Assumption": 0.8, "Limitation": 0.9, "FailureCondition": 0.9,
            "TrainingSignal": 0.8, "Feedback": 0.8, "Result": 0.8,
            "Dataset": 0.5, "Metric": 0.5, "Embodiment": 0.5,
        }
        pairs = []
        papers = sorted(by_paper)
        for index, source in enumerate(papers):
            for target in papers[index + 1:]:
                signals = []
                weighted_scores = []
                for node_type, weight in weights.items():
                    left = profiles[source].get(node_type, set())
                    right = profiles[target].get(node_type, set())
                    if not left or not right:
                        continue
                    exact = sorted(left & right)
                    best = 0.0
                    best_pair = None
                    if exact:
                        best = 1.0
                        best_pair = (exact[0], exact[0])
                    else:
                        for left_key in left:
                            left_tokens = self._key_tokens(left_key)
                            for right_key in right:
                                right_tokens = self._key_tokens(right_key)
                                union = left_tokens | right_tokens
                                score = len(left_tokens & right_tokens) / len(union) if union else 0.0
                                if score > best:
                                    best = score
                                    best_pair = (left_key, right_key)
                    if best > 0 and best_pair:
                        weighted_scores.append((best, weight))
                        signals.append({
                            "dimension": node_type, "similarity": round(best, 4),
                            "source_key": best_pair[0], "target_key": best_pair[1],
                        })
                if not weighted_scores:
                    continue
                score = sum(value * weight for value, weight in weighted_scores) / sum(
                    weight for _, weight in weighted_scores
                )
                pairs.append({
                    "from": source, "to": target, "recall_score": round(score, 4),
                    "signals": sorted(signals, key=lambda item: (-item["similarity"], item["dimension"])),
                })
        pairs.sort(key=lambda item: (-item["recall_score"], item["from"], item["to"]))
        titles = {
            item["id"]: self.project.evidence.show(item["id"])["metadata"].get("title", item["id"])
            for item in corpus["papers"]
        }
        selected = []
        for pair in pairs[:top_k]:
            selected.append({
                **pair,
                "papers": [
                    {
                        "paper_id": paper_id, "title": titles[paper_id],
                        "extraction_schema_version": max(
                            int(item.get("_extraction_schema_version", 1)) for item in by_paper[paper_id]
                        ),
                        "tuples": [
                            {
                                "id": item["id"], "subject": item["subject"],
                                "relation": item["relation"], "object": item["object"],
                                "assertion": item.get("assertion"), "evidence": item["evidence"],
                            }
                            for item in by_paper[paper_id]
                        ],
                    }
                    for paper_id in (pair["from"], pair["to"])
                ],
            })
        packet_fingerprint = canonical_hash({
            "semantic_input": input_fingerprint, "algorithm": "pair-recall-v1",
            "top_k": top_k, "pairs": selected,
        })
        return {
            "schema_version": 1, "corpus_id": corpus_id,
            "semantic_input_fingerprint": input_fingerprint,
            "vocabulary_fingerprint": concepts.fingerprint(),
            "packet_fingerprint": packet_fingerprint, "algorithm": "pair-recall-v1",
            "top_k": top_k, "pair_count": len(selected), "pairs": selected,
            "meaning": (
                "Pair recall proposes comparisons for an Agent or human; it does not assign or accept a relationship."
            ),
        }

    def evaluate(self, corpus_id: str, benchmark_file: Path, *, mode: str = "semantic") -> dict[str, Any]:
        benchmark = read_yaml(benchmark_file.expanduser().resolve())
        validate_record("adjacency_benchmark", benchmark)
        if benchmark["corpus_id"] != corpus_id:
            raise ResearchFlowError("Adjacency benchmark Corpus does not match --corpus.")
        corpus = self.corpora.show(corpus_id)["record"]
        if benchmark["corpus_fingerprint"] != corpus["corpus_fingerprint"]:
            raise ResearchFlowError("Adjacency benchmark is stale for the current Corpus fingerprint.")
        benchmark_content = {
            key: benchmark[key]
            for key in ("schema_version", "benchmark_id", "corpus_id", "corpus_fingerprint", "rationale", "cases")
        }
        benchmark_fingerprint = canonical_hash(benchmark_content)
        if benchmark["review"]["reviewed_fingerprint"] != benchmark_fingerprint:
            raise ResearchFlowError("Adjacency benchmark human review fingerprint is stale.")
        corpus_papers = {item["id"] for item in corpus["papers"]}
        seen: set[tuple[str, str, str]] = set()
        normalized_cases = []
        for case in benchmark["cases"]:
            marker = (case["from"], case["relation"], case["to"])
            if case["from"] == case["to"]:
                raise ResearchFlowError("Adjacency benchmark cannot contain a self-pair.")
            if case["from"] not in corpus_papers or case["to"] not in corpus_papers:
                raise ResearchFlowError("Adjacency benchmark contains a Paper outside the Corpus.")
            if case["relation"] in SYMMETRIC_RELATIONS and case["from"] > case["to"]:
                marker = (case["to"], case["relation"], case["from"])
            if marker in seen:
                raise ResearchFlowError("Adjacency benchmark contains a duplicate case.")
            seen.add(marker)
            normalized_cases.append((case, marker))
        preview = self.preview(corpus_id, mode=mode)
        predicted = {(item["from"], item["relation"], item["to"]) for item in preview["candidates"]}
        ontology_relations = {
            (item["from"], item["relation"], item["to"])
            for item in preview["candidates"]
            if item["relation"] in SYMMETRIC_RELATIONS
            and item["generator"]["kind"] == "deterministic_semantic"
            and "accepted " in item["rationale"]
            and " concept" in item["rationale"]
        }
        conflicts = [
            marker for case, marker in normalized_cases
            if case["expected"] is False and marker in ontology_relations
        ]
        if conflicts:
            labels = ", ".join(f"{source} --{relation}-- {target}" for source, relation, target in conflicts)
            raise ResearchFlowError(
                "Adjacency benchmark conflicts with accepted ontology: " + labels
            )
        tp = fp = fn = tn = 0
        cases = []
        for case, marker in normalized_cases:
            found = marker in predicted
            expected = case["expected"]
            if expected and found:
                tp += 1
            elif expected:
                fn += 1
            elif found:
                fp += 1
            else:
                tn += 1
            cases.append({**case, "predicted": found, "correct": expected == found})

        def ratio(numerator: int, denominator: int) -> float | None:
            return round(numerator / denominator, 4) if denominator else None

        precision = ratio(tp, tp + fp)
        recall = ratio(tp, tp + fn)
        f1 = (
            round(2 * precision * recall / (precision + recall), 4)
            if precision is not None and recall is not None and precision + recall else None
        )
        return {
            "benchmark_id": benchmark["benchmark_id"], "corpus_id": corpus_id,
            "mode": mode, "reviewer": benchmark["review"]["reviewer"],
            "benchmark_fingerprint": benchmark_fingerprint,
            "input_fingerprint": preview["input_fingerprint"],
            "candidate_count": preview["candidate_count"],
            "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "metrics": {"precision": precision, "recall": recall, "f1": f1},
            "unscored_candidates": len(predicted - seen),
            "cases": cases,
            "meaning": "Metrics apply only to the named human-reviewed benchmark cases, not scientific validity.",
        }

    def _normalize_request(self, request_file: Path) -> dict[str, Any]:
        request = read_yaml(request_file.expanduser().resolve())
        validate_record("paper_adjacency_request", request)
        if request["from"] == request["to"]:
            raise ResearchFlowError("Paper adjacency cannot be a self-loop.")
        if request["relation"] in SYMMETRIC_RELATIONS and request["directed"]:
            raise ResearchFlowError(f"{request['relation']} must be undirected.")
        if request["relation"] not in SYMMETRIC_RELATIONS and not request["directed"]:
            raise ResearchFlowError(f"{request['relation']} must be directed.")
        corpus, tuples, extraction_fingerprints = self._corpus_inputs(request["corpus_id"])
        corpus_papers = {item["id"]: item for item in corpus["papers"]}
        if request["from"] not in corpus_papers or request["to"] not in corpus_papers:
            raise ResearchFlowError("Both adjacency endpoints must be members of the selected Corpus.")
        if {item["paper_id"] for item in request["evidence"]} != {request["from"], request["to"]}:
            raise ResearchFlowError("Adjacency evidence must cover exactly both Paper endpoints.")
        tuples_by_id = {item["id"]: item for item in tuples}
        for evidence in request["evidence"]:
            paper = self.project.evidence.show(evidence["paper_id"])
            for claim_id in evidence["claim_ids"]:
                if claim_id not in paper["body"]:
                    raise ResearchFlowError(f"Adjacency references missing claim {claim_id} in {evidence['paper_id']}.")
            for tuple_id in evidence["tuple_ids"]:
                if tuple_id not in tuples_by_id or tuples_by_id[tuple_id]["paper_id"] != evidence["paper_id"]:
                    raise ResearchFlowError(f"Adjacency references unavailable accepted tuple {tuple_id} for {evidence['paper_id']}.")
            for locator in evidence["locators"]:
                if locator["kind"] == "path":
                    _safe_workspace_path(self.project, locator["value"])
        normalized = dict(request)
        if request.get("semantic_context"):
            from .concepts import ConceptStore
            current_vocabulary = ConceptStore(self.project).fingerprint()
            if request["semantic_context"]["vocabulary_fingerprint"] != current_vocabulary:
                raise ResearchFlowError("Adjacency semantic context uses a stale concept vocabulary.")
        if request["relation"] in SYMMETRIC_RELATIONS and request["from"] > request["to"]:
            normalized["from"], normalized["to"] = request["to"], request["from"]
            normalized["evidence"] = sorted(request["evidence"], key=lambda item: item["paper_id"])
        generator = dict(normalized["generator"])
        generator["input_fingerprint"] = canonical_hash({
            "request": {**normalized, "generator": {key: generator[key] for key in ("kind", "name", "version")}},
            "corpus": corpus["corpus_fingerprint"], "extractions": extraction_fingerprints,
        })
        normalized["generator"] = generator
        normalized["dimensions"] = sorted(set(normalized["dimensions"]))
        fingerprints = {}
        for paper_id in (normalized["from"], normalized["to"]):
            paper = self.project.evidence.show(paper_id)
            fingerprints[paper_id] = canonical_hash({"metadata": paper["metadata"], "body": paper["body"]})
        normalized["source_fingerprints"] = fingerprints
        normalized["adjacency_fingerprint"] = adjacency_fingerprint(normalized)
        return normalized

    def preflight(self, request_file: Path) -> dict[str, Any]:
        normalized = self._normalize_request(request_file)
        existing = next(
            (item for item in self.load()["edges"] if item["adjacency_fingerprint"] == normalized["adjacency_fingerprint"]),
            None,
        )
        return {
            "valid": True, "adjacency_fingerprint": normalized["adjacency_fingerprint"],
            "idempotent_existing_id": existing["id"] if existing else None,
            "meaning": "Structure, accepted extraction references, Paper claims, and locators pass; semantic relation remains review-pending.",
        }

    def add_file(self, request_file: Path, *, dry_run: bool = False) -> dict[str, Any]:
        normalized = self._normalize_request(request_file)
        existing = next(
            (item for item in self.load()["edges"] if item["adjacency_fingerprint"] == normalized["adjacency_fingerprint"]),
            None,
        )
        if existing:
            return {"edge": existing, "created": False, "idempotent": True, "dry_run": dry_run}
        if dry_run:
            return {"created": False, "idempotent": False, "dry_run": True, **normalized}
        with exclusive_lock(self.project.root / LOCK_RELATIVE_PATH):
            ledger = self.load()
            existing = next(
                (item for item in ledger["edges"] if item["adjacency_fingerprint"] == normalized["adjacency_fingerprint"]),
                None,
            )
            if existing:
                return {"edge": existing, "created": False, "idempotent": True, "dry_run": False}
            edge = {
                "id": allocate_id(research_home(), "PADJ"), **normalized,
                "status": "candidate",
                "review": {"status": "pending", "reviewer": None, "reviewed_fingerprint": None, "rationale": None, "reviewed_at": None},
                "reviews": [], "created_at": utc_now(),
            }
            self._write({**ledger, "edges": [*ledger["edges"], edge]})
            return {"edge": edge, "created": True, "idempotent": False, "dry_run": False}

    @staticmethod
    def _relation_counts(edges: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for edge in edges:
            counts[edge["relation"]] = counts.get(edge["relation"], 0) + 1
        return dict(sorted(counts.items()))

    def _is_current(
        self, edge: dict[str, Any], cache: dict[str, Any] | None = None
    ) -> tuple[bool, list[str]]:
        cache = cache if cache is not None else {}
        corpus_cache = cache.setdefault("corpus_inputs", {})
        paper_cache = cache.setdefault("papers", {})
        build_cache = cache.setdefault("build_inputs", {})
        issues = []
        try:
            if edge["corpus_id"] not in corpus_cache:
                corpus_cache[edge["corpus_id"]] = self._corpus_inputs(edge["corpus_id"])
            corpus, tuples, _ = corpus_cache[edge["corpus_id"]]
            papers = {item["id"]: item["source_fingerprint"] for item in corpus["papers"]}
            tuples_by_id = {item["id"]: item for item in tuples}
            for paper_id in (edge["from"], edge["to"]):
                if paper_id not in paper_cache:
                    paper_cache[paper_id] = self.project.evidence.show(paper_id)
                paper = paper_cache[paper_id]
                document_fingerprint = paper["metadata"].get("source", {}).get("document", {}).get("sha256", "")
                if papers.get(paper_id, "").casefold() != document_fingerprint.casefold():
                    issues.append(f"Corpus source fingerprint changed for {paper_id}")
                analysis_fingerprint = canonical_hash({"metadata": paper["metadata"], "body": paper["body"]})
                if analysis_fingerprint != edge["source_fingerprints"].get(paper_id):
                    issues.append(f"Paper analysis fingerprint changed for {paper_id}")
            for evidence in edge["evidence"]:
                for tuple_id in evidence["tuple_ids"]:
                    item = tuples_by_id.get(tuple_id)
                    if not item or item["paper_id"] != evidence["paper_id"]:
                        issues.append(
                            f"Accepted extraction no longer provides {tuple_id} for {evidence['paper_id']}"
                        )
        except ResearchFlowError as exc:
            issues.append(str(exc))
        if adjacency_fingerprint(edge) != edge["adjacency_fingerprint"]:
            issues.append("adjacency content fingerprint changed")
        semantic_context = edge.get("semantic_context")
        if semantic_context:
            from .concepts import ConceptStore
            if "vocabulary_fingerprint" not in cache:
                cache["vocabulary_fingerprint"] = ConceptStore(self.project).fingerprint()
            if semantic_context["vocabulary_fingerprint"] != cache["vocabulary_fingerprint"]:
                issues.append("accepted concept vocabulary changed")
        if edge["generator"]["kind"] == "deterministic_semantic":
            try:
                marker = (edge["corpus_id"], "semantic")
                if marker not in build_cache:
                    build_cache[marker] = self._build_inputs(edge["corpus_id"], "semantic")
                _, _, current_input = build_cache[marker]
                if current_input != edge["generator"]["input_fingerprint"]:
                    issues.append("semantic adjacency inputs changed")
            except ResearchFlowError as exc:
                issues.append(str(exc))
        review = edge["review"]
        if edge["status"] == "accepted" and review["reviewed_fingerprint"] != edge["adjacency_fingerprint"]:
            issues.append("accepted review is stale")
        return not issues, issues

    def list(self, *, status: str | None = None, corpus_id: str | None = None) -> list[dict[str, Any]]:
        values = []
        cache: dict[str, Any] = {}
        for edge in self.load()["edges"]:
            current, issues = self._is_current(edge, cache)
            item = {**edge, "current": current, "issues": issues}
            if status and edge["status"] != status:
                continue
            if corpus_id and edge["corpus_id"] != corpus_id:
                continue
            values.append(item)
        return values

    def show(self, edge_id: str) -> dict[str, Any]:
        edge = next((item for item in self.load()["edges"] if item["id"] == edge_id), None)
        if not edge:
            raise ResearchFlowError(f"Paper adjacency not found: {edge_id}")
        current, issues = self._is_current(edge)
        return {"edge": edge, "current": current, "issues": issues, "usable_for_gap": current and edge["status"] == "accepted"}

    def review(
        self, edge_id: str, *, decision: str, reviewer: str, rationale: str, dry_run: bool = False
    ) -> dict[str, Any]:
        if decision not in {"accepted", "revision_requested", "rejected"}:
            raise ResearchFlowError("Adjacency decision must be accepted, revision_requested, or rejected.")
        if decision == "accepted" and (not reviewer.startswith("human:") or not reviewer.removeprefix("human:").strip()):
            raise ResearchFlowError("Only a human:* reviewer may accept a Paper adjacency.")
        if not reviewer.strip() or not rationale.strip():
            raise ResearchFlowError("Adjacency review needs a reviewer and rationale.")

        def prepare(ledger: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            index = next((i for i, item in enumerate(ledger["edges"]) if item["id"] == edge_id), None)
            if index is None:
                raise ResearchFlowError(f"Paper adjacency not found: {edge_id}")
            edge = ledger["edges"][index]
            current, issues = self._is_current(edge)
            if not current:
                raise ResearchFlowError("Cannot review stale Paper adjacency: " + "; ".join(issues))
            review = {
                "status": decision, "reviewer": reviewer.strip(),
                "reviewed_fingerprint": edge["adjacency_fingerprint"],
                "rationale": rationale.strip(), "reviewed_at": utc_now(),
            }
            updated = {**edge, "status": decision, "review": review, "reviews": [*edge["reviews"], review]}
            edges = list(ledger["edges"])
            edges[index] = updated
            return review, {**ledger, "edges": edges}

        if dry_run:
            review, _ = prepare(self.load())
        else:
            with exclusive_lock(self.project.root / LOCK_RELATIVE_PATH):
                review, candidate = prepare(self.load())
                self._write(candidate)
        return {"id": edge_id, "review": review, "dry_run": dry_run}

    def neighbors(self, paper_id: str, *, status: str = "accepted", top_k: int = 10) -> dict[str, Any]:
        self.project.evidence.show(paper_id)
        if top_k < 1:
            raise ResearchFlowError("--top-k must be positive.")
        if status not in {"candidate", "accepted", "revision_requested", "rejected", "all"}:
            raise ResearchFlowError("Unknown adjacency status filter.")
        edges = [
            item for item in self.list(status=None if status == "all" else status)
            if item["current"] and paper_id in {item["from"], item["to"]}
        ]
        edges.sort(key=lambda item: (-item["score"]["overall"], item["relation"], item["id"]))
        values = []
        for edge in edges[:top_k]:
            neighbor = edge["to"] if edge["from"] == paper_id else edge["from"]
            values.append({
                "neighbor": neighbor, "edge_id": edge["id"], "relation": edge["relation"],
                "direction": "outgoing" if edge["from"] == paper_id else "incoming",
                "score": edge["score"], "rationale": edge["rationale"], "status": edge["status"],
            })
        return {"paper_id": paper_id, "status_filter": status, "neighbors": values, "count": len(values)}

    def explain(self, source: str, target: str) -> dict[str, Any]:
        self.project.evidence.show(source)
        self.project.evidence.show(target)
        edges = [item for item in self.list() if item["current"] and {item["from"], item["to"]} == {source, target}]
        return {"from": source, "to": target, "edges": edges, "count": len(edges)}

    def check(self) -> dict[str, Any]:
        ledger = self.load()
        issues = []
        usable = 0
        cache: dict[str, Any] = {}
        for edge in ledger["edges"]:
            current, edge_issues = self._is_current(edge, cache)
            issues.extend(f"{edge['id']}: {issue}" for issue in edge_issues)
            if current and edge["status"] == "accepted":
                usable += 1
        build_fingerprints = [item["input_fingerprint"] for item in ledger["builds"]]
        if len(build_fingerprints) != len(set(build_fingerprints)):
            issues.append("duplicate build input fingerprint")
        return {
            "initialized": self.path.exists(), "valid": not issues, "issues": issues,
            "builds": len(ledger["builds"]), "edges": len(ledger["edges"]),
            "accepted_current": usable,
            "meaning": "Accepted current adjacency supports literature navigation and Gap analysis; it does not establish novelty.",
        }

    def export(self, output: Path, *, format: str = "json", dry_run: bool = False) -> dict[str, Any]:
        edges = self.list()
        target = output.expanduser().resolve()
        try:
            target.relative_to(self.project.root.resolve())
        except ValueError as exc:
            raise ResearchFlowError("Paper adjacency export must remain inside the project workspace.") from exc
        if format == "json":
            content = json.dumps({"edges": edges}, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        elif format == "dot":
            lines = ["digraph PaperAdjacency {"]
            for edge in edges:
                style = "solid" if edge["status"] == "accepted" and edge["current"] else "dashed"
                lines.append(f'  "{edge["from"]}" -> "{edge["to"]}" [label="{edge["relation"]}", style="{style}"];')
            lines.append("}")
            content = "\n".join(lines) + "\n"
        else:
            raise ResearchFlowError("Adjacency export format must be json or dot.")
        if not dry_run:
            atomic_text(target, content)
        return {"output": str(target), "format": format, "edges": len(edges), "dry_run": dry_run}

    def promote(self, edge_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        shown = self.show(edge_id)
        if not shown["usable_for_gap"]:
            raise ResearchFlowError("Only a current human-accepted Paper adjacency can enter EvidenceGraph.")
        edge = shown["edge"]
        from .evidence_graph import EvidenceGraphStore
        return EvidenceGraphStore(self.project).connect(
            edge["from"], edge["relation"], edge["to"],
            provenance_refs=[edge_id], dry_run=dry_run,
        )

    def summary(self) -> dict[str, Any]:
        result = self.check()
        from .concepts import ConceptStore
        concepts = ConceptStore(self.project).check()
        return {
            **{key: result[key] for key in ("initialized", "valid", "builds", "edges", "accepted_current")},
            "concepts": {
                key: concepts[key]
                for key in ("initialized", "valid", "concepts", "accepted", "fingerprint")
            },
        }
