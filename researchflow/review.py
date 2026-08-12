from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .errors import ResearchFlowError
from .io import atomic_text, markdown_record, read_markdown_record, utc_now
from .schema import validate_record


MEANING = {
    "contract_valid": "Required fields and file contract pass structural checks.",
    "source_verified": "The analysis is bound to an identified primary source.",
    "fingerprint_verified": "The recorded source fingerprint is present and valid.",
    "human_reviewed": "A named human accepted the stated review scope for the current fingerprint.",
    "reproduction_unverified": "No independent method reproduction is established by this record.",
    "scientific_claim_unestablished": "No scientific conclusion is established merely by contract, source, or review status.",
}


def matrix_fingerprint(record: dict[str, Any]) -> str:
    content = {key: value for key, value in record.items() if key not in {"reviews", "updated_at"}}
    payload = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def review_status(reviews: list[dict[str, Any]], current_fingerprint: str | None) -> dict[str, Any]:
    enriched = []
    for review in reviews:
        stale = not current_fingerprint or review["reviewed_source_fingerprint"].casefold() != current_fingerprint.casefold()
        enriched.append({**review, "stale": stale, "current": not stale})
    current_accepted = any(review["current"] and review["decision"] == "accepted" for review in enriched)
    return {
        "reviews": enriched,
        "human_reviewed": current_accepted,
        "semantic_review_pending": not current_accepted,
        "stale_reviews": sum(review["stale"] for review in enriched),
    }


def add_paper_review(
    project,
    paper_id: str,
    *,
    reviewer: str,
    decision: str,
    scope: str,
    notes: str | None = None,
    notes_path: Path | None = None,
) -> dict[str, Any]:
    path = project.root / "evidence" / "papers" / "analysis" / f"{paper_id}.md"
    if not path.is_file():
        raise ResearchFlowError(f"Paper evidence not found: {paper_id}")
    metadata, body = read_markdown_record(path)
    fingerprint = metadata.get("source", {}).get("document", {}).get("sha256")
    if not fingerprint:
        raise ResearchFlowError(f"{paper_id} must be source/fingerprint verified before human review.")
    note_ref = _review_notes_path(project, notes_path)
    record = _review_record(reviewer, decision, scope, fingerprint, notes, note_ref)
    candidate = dict(metadata)
    candidate["reviews"] = [*metadata.get("reviews", []), record]
    state = review_status(candidate["reviews"], fingerprint)
    verification = _paper_verification(metadata, state)
    candidate["verification"] = verification
    validate_record("paper", candidate)
    atomic_text(path, markdown_record(candidate, body))
    return {"paper_id": paper_id, "review": {**record, "stale": False}, "verification": verification, "meaning": MEANING}


def paper_verification(metadata: dict[str, Any]) -> dict[str, Any]:
    fingerprint = metadata.get("source", {}).get("document", {}).get("sha256")
    state = review_status(metadata.get("reviews", []), fingerprint)
    return {**_paper_verification(metadata, state), **state, "meaning": MEANING}


def add_matrix_review(
    matrix,
    *,
    reviewer: str,
    decision: str,
    scope: str,
    notes: str | None = None,
    notes_path: Path | None = None,
) -> dict[str, Any]:
    record = matrix.load()
    fingerprint = matrix_fingerprint(record)
    note_ref = _review_notes_path(matrix.project, notes_path)
    review = _review_record(reviewer, decision, scope, fingerprint, notes, note_ref)
    candidate = {**record, "reviews": [*record.get("reviews", []), review]}
    matrix.replace(candidate)
    return {"matrix_id": record["id"], "review": {**review, "stale": False}, "meaning": MEANING}


def matrix_review_status(record: dict[str, Any]) -> dict[str, Any]:
    status = review_status(record.get("reviews", []), matrix_fingerprint(record))
    return {**status, "content_fingerprint": matrix_fingerprint(record), "meaning": MEANING}


def _paper_verification(metadata: dict[str, Any], state: dict[str, Any]) -> dict[str, bool]:
    document = metadata.get("source", {}).get("document") or {}
    source_verified = metadata.get("status") == "verified" and bool(document)
    return {
        "contract_valid": True,
        "source_verified": source_verified,
        "fingerprint_verified": source_verified and bool(document.get("sha256")),
        "semantic_review_pending": state["semantic_review_pending"],
        "human_reviewed": state["human_reviewed"],
        "reproduction_unverified": True,
        "scientific_claim_unestablished": True,
    }


def _review_record(reviewer: str, decision: str, scope: str, fingerprint: str, notes: str | None, notes_path: str | None) -> dict[str, Any]:
    if decision not in {"accepted", "revision_requested", "rejected"}:
        raise ResearchFlowError("Review decision must be accepted, revision_requested, or rejected.")
    if not reviewer.strip() or not scope.strip():
        raise ResearchFlowError("Review reviewer and scope must be non-empty.")
    return {
        "reviewer": reviewer.strip(), "decision": decision, "reviewed_at": utc_now(),
        "scope": scope.strip(), "notes": notes.strip() if notes else None,
        "notes_path": notes_path, "reviewed_source_fingerprint": fingerprint,
    }


def _review_notes_path(project, notes_path: Path | None) -> str | None:
    if not notes_path:
        return None
    root = project.root.resolve()
    path = notes_path.expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ResearchFlowError(f"Review notes path escapes the project workspace: {path}") from exc
    if not path.is_file():
        raise ResearchFlowError(f"Review notes path does not exist: {path}")
    return relative


def migrate_paper_verification(project, *, dry_run: bool = False) -> dict[str, Any]:
    candidates = []
    for path in sorted((project.root / "evidence" / "papers" / "analysis").glob("PAPER-*.md")):
        metadata, _ = read_markdown_record(path)
        if metadata.get("status") == "verified" and "verification" not in metadata:
            candidates.append(path)
    result = {
        "migration": "paper-verification-v1",
        "files": [path.relative_to(project.root).as_posix() for path in candidates],
        "count": len(candidates), "dry_run": dry_run,
        "changed": bool(candidates) and not dry_run,
        "risk": "Adds explicit verification semantics without changing the source analysis body; human review remains pending unless recorded separately.",
        "rollback": "Restore the backup snapshot created before a non-dry-run migration.",
    }
    if dry_run or not candidates:
        return result
    from .snapshot import create_snapshot
    backup = create_snapshot(project)
    for path in candidates:
        metadata, body = read_markdown_record(path)
        computed = paper_verification(metadata)
        metadata["verification"] = {
            key: computed[key] for key in (
                "contract_valid", "source_verified", "fingerprint_verified", "semantic_review_pending",
                "human_reviewed", "reproduction_unverified", "scientific_claim_unestablished",
            )
        }
        validate_record("paper", metadata)
        atomic_text(path, markdown_record(metadata, body))
    result["backup_snapshot"] = backup["snapshot"]
    return result
