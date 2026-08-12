from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .config import load_config, research_home
from .errors import ResearchFlowError
from .ids import allocate_id
from .io import append_jsonl, atomic_text, markdown_record, read_jsonl, read_markdown_record, read_yaml, utc_now, write_yaml
from .project import ResearchProject
from .schema import validate_record
from .zotero import ZoteroClient, item_metadata

DEEP_READ_BODY = """# {title}

## Source Snapshot

- Primary document inspected: not yet
- Version and file hash: not yet recorded
- Citation basis: PDF page number printed by the reader

## TL;DR

Needs verification.

## Problem

## Core Method

## Architecture

## Training

## Evaluation

## Key Results

## Claim Strength Scale

- **S1 - direct quantitative:** a number transcribed from a named table, figure, or experiment in the primary document.
- **S2 - direct descriptive:** an architecture, procedure, or limitation explicitly stated or shown in the primary document.
- **S3 - author interpretation:** the authors' explanation or generalization from their evidence; not independently established.
- **S4 - analyst inference:** a project-specific interpretation or idea derived from the paper; not a paper claim.

Strength labels describe the source relationship, not whether a claim is universally true or independently reproduced.

## Verified Claims

| ID | Claim | Strength | PDF page(s) | Locator | Scope / qualifier |
|---|---|---|---|---|---|
| C01 | Needs verification. | - | - | - | - |

## Critical Assessment

## Limitations

## Relevance to Project

## Idea Seeds

### IDEA-01 - Untitled

- **Trigger:** Which paper result, limitation, or contradiction prompted the idea?
- **Proposed mechanism:** What change might cause what effect, and why?
- **Supporting evidence:** Claim IDs and PDF page citations.
- **Counterevidence / risk:** What could make the mechanism wrong or impractical?
- **Novelty status:** Unchecked until a separate current literature search is completed.
- **Smallest falsification test:** The cheapest observation or experiment that can reject it.
- **Promotion rule:** Keep as an idea seed until converted into a falsifiable `HYP-*` record.

## Open Questions
"""

PAPER_BODY = DEEP_READ_BODY

ZOTERO_PAPER_BODY = """# {title}

## Source Authority

Zotero owns the bibliography, PDF, collections, tags, notes, annotations, and citation formatting. ResearchFlow stores only this source reference and the analysis below.
""" + DEEP_READ_BODY.split("\n", 1)[1]


DEEP_READ_REQUIRED_HEADINGS = (
    "Source Snapshot",
    "Claim Strength Scale",
    "Verified Claims",
    "Critical Assessment",
    "Idea Seeds",
)


class EvidenceStore:
    def __init__(self, project: ResearchProject):
        self.project = project

    def add_paper(self, pdf: Path, title: str, authors: list[str] | None = None, venue: str | None = None, year: int | None = None, url: str | None = None, tags: list[str] | None = None) -> str:
        literature = load_config().get("preferences", {}).get("literature", {})
        if literature.get("authority") == "zotero":
            raise ResearchFlowError(
                "Manual PDF copying is disabled because Zotero is the literature authority. Add the item/PDF in Zotero, then run: rf evidence zotero link <ITEM-KEY>"
            )
        pdf = pdf.expanduser().resolve()
        if not pdf.is_file():
            raise ResearchFlowError(f"Paper PDF does not exist: {pdf}")
        if pdf.suffix.lower() != ".pdf":
            raise ResearchFlowError(f"Expected a PDF file, got: {pdf}")
        record_id = allocate_id(research_home(), "PAPER")
        target = self.project.root / "evidence" / "papers" / "pdf" / f"{record_id}.pdf"
        shutil.copy2(pdf, target)
        relative_pdf = target.relative_to(self.project.root).as_posix()
        metadata = {
            "id": record_id, "title": title, "authors": authors or [], "venue": venue,
            "year": year, "source": {"url": url, "local_pdf": relative_pdf},
            "tags": tags or [], "methods": [], "status": "unread", "core_operator": None,
            "primary_logic": None, "verified_at": None,
        }
        validate_record("paper", metadata)
        analysis = self.project.root / "evidence" / "papers" / "analysis" / f"{record_id}.md"
        atomic_text(analysis, markdown_record(metadata, PAPER_BODY.format(title=title)))
        append_jsonl(self.project.root / "evidence" / "papers" / "index.jsonl", {
            "id": record_id, "title": title, "year": year, "venue": venue,
            "tags": tags or [], "methods": [],
            "analysis_path": analysis.relative_to(self.project.root).as_posix(),
            "pdf_path": relative_pdf,
        })
        return record_id

    def link_zotero(self, client: ZoteroClient, item_key: str) -> str:
        item = client.item(item_key)
        source_ref = {
            "server_id": client.server_id,
            "library": client.library,
            "item_key": item.get("key") or item_key,
            "item_version": item.get("version") or item.get("data", {}).get("version"),
            "linked_at": utc_now(),
        }
        for existing in self.list("paper"):
            zotero = existing.get("zotero") or {}
            if all(zotero.get(key) == source_ref.get(key) for key in ("server_id", "library", "item_key")):
                return str(existing["id"])
        extracted = item_metadata(item)
        record_id = allocate_id(research_home(), "PAPER")
        metadata = {
            "id": record_id,
            "title": extracted["title"],
            "authors": extracted["authors"],
            "venue": extracted["venue"],
            "year": extracted["year"],
            "source": {"url": extracted["url"], "local_pdf": None, "zotero": source_ref},
            "tags": extracted["tags"],
            "methods": [],
            "status": "unread",
            "core_operator": None,
            "primary_logic": None,
            "verified_at": None,
        }
        validate_record("paper", metadata)
        analysis = self.project.root / "evidence" / "papers" / "analysis" / f"{record_id}.md"
        atomic_text(analysis, markdown_record(metadata, ZOTERO_PAPER_BODY.format(title=extracted["title"])))
        append_jsonl(self.project.root / "evidence" / "papers" / "index.jsonl", self._paper_index(metadata, analysis))
        return record_id

    def refresh_zotero(self, record_id: str, client: ZoteroClient) -> str:
        path = self.project.root / "evidence" / "papers" / "analysis" / f"{record_id}.md"
        if not path.exists():
            raise ResearchFlowError(f"Paper evidence not found: {record_id}")
        metadata, body = read_markdown_record(path)
        source_ref = metadata.get("source", {}).get("zotero")
        if not source_ref:
            raise ResearchFlowError(f"Paper {record_id} is not linked to Zotero.")
        if client.library != source_ref.get("library"):
            raise ResearchFlowError(f"Paper {record_id} belongs to Zotero library {source_ref.get('library')}.")
        item = client.item(str(source_ref["item_key"]))
        if source_ref.get("server_id") and client.server_id and source_ref["server_id"] != client.server_id:
            raise ResearchFlowError("Zotero database identity differs from the linked paper; refusing to refresh.")
        extracted = item_metadata(item)
        metadata.update({key: extracted[key] for key in ("title", "authors", "venue", "year", "tags")})
        metadata["source"]["url"] = extracted["url"]
        metadata["source"]["zotero"]["server_id"] = client.server_id
        metadata["source"]["zotero"]["item_version"] = extracted["item_version"]
        metadata["source"]["zotero"]["linked_at"] = utc_now()
        validate_record("paper", metadata)
        atomic_text(path, markdown_record(metadata, body))
        self._replace_paper_index(record_id, self._paper_index(metadata, path))
        return record_id

    def verify_paper(
        self,
        record_id: str,
        *,
        sha256: str,
        source_version: str,
        page_count: int,
        core_operator: str,
        primary_logic: str,
        methods: list[str],
    ) -> str:
        """Finalize a primary-source deep read and synchronize its searchable index."""
        path = self.project.root / "evidence" / "papers" / "analysis" / f"{record_id}.md"
        if not path.exists():
            raise ResearchFlowError(f"Paper evidence not found: {record_id}")
        metadata, body = read_markdown_record(path)
        self._validate_deep_read(body)
        normalized_hash = sha256.upper()
        if not re.fullmatch(r"[0-9A-F]{64}", normalized_hash):
            raise ResearchFlowError("--sha256 must be exactly 64 hexadecimal characters.")
        if page_count < 1:
            raise ResearchFlowError("--pages must be a positive PDF page count.")
        if not source_version.strip() or not core_operator.strip() or not primary_logic.strip():
            raise ResearchFlowError("Source version, core operator, and primary logic must be non-empty.")
        normalized_methods = list(dict.fromkeys(item.strip() for item in methods if item.strip()))
        if not normalized_methods:
            raise ResearchFlowError("At least one method is required for a verified paper.")

        verified_at = utc_now()
        metadata["source"]["document"] = {
            "sha256": normalized_hash,
            "version": source_version.strip(),
            "page_count": page_count,
            "citation_basis": "pdf_page",
            "inspected_at": verified_at,
        }
        metadata["methods"] = normalized_methods
        metadata["status"] = "verified"
        metadata["core_operator"] = core_operator.strip()
        metadata["primary_logic"] = primary_logic.strip()
        metadata["verified_at"] = verified_at
        from .review import paper_verification
        computed = paper_verification(metadata)
        metadata["verification"] = {
            key: computed[key] for key in (
                "contract_valid", "source_verified", "fingerprint_verified", "semantic_review_pending",
                "human_reviewed", "reproduction_unverified", "scientific_claim_unestablished",
            )
        }
        validate_record("paper", metadata)
        atomic_text(path, markdown_record(metadata, body))
        self._replace_paper_index(record_id, self._paper_index(metadata, path))
        return record_id

    @staticmethod
    def _validate_deep_read(body: str) -> None:
        missing = [heading for heading in DEEP_READ_REQUIRED_HEADINGS if f"## {heading}" not in body]
        if missing:
            raise ResearchFlowError(f"Deep-read analysis is missing required sections: {', '.join(missing)}")
        if "Needs verification." in body or "No claims verified yet." in body:
            raise ResearchFlowError("Deep-read analysis still contains an unread placeholder.")
        if not re.search(r"\b(?:p|pp)\.\s*\d+", body, flags=re.IGNORECASE):
            raise ResearchFlowError("Deep-read analysis needs at least one PDF page citation such as 'p. 6'.")
        if not re.search(r"\bC\d{2}\b", body):
            raise ResearchFlowError("Deep-read analysis needs at least one claim ID such as C01.")
        if not re.search(r"\bIDEA-\d{2}\b", body):
            raise ResearchFlowError("Deep-read analysis needs at least one structured idea seed such as IDEA-01.")

    def _paper_index(self, metadata: dict[str, Any], analysis: Path) -> dict[str, Any]:
        zotero = metadata.get("source", {}).get("zotero")
        return {
            "id": metadata["id"], "title": metadata["title"], "year": metadata["year"],
            "venue": metadata["venue"], "tags": metadata["tags"],
            "methods": metadata.get("methods", []), "status": metadata["status"],
            "core_operator": metadata.get("core_operator"),
            "primary_logic": metadata.get("primary_logic"),
            "analysis_path": analysis.relative_to(self.project.root).as_posix(),
            "pdf_path": metadata.get("source", {}).get("local_pdf"),
            "zotero": zotero,
        }

    def _replace_paper_index(self, record_id: str, replacement: dict[str, Any]) -> None:
        path = self.project.root / "evidence" / "papers" / "index.jsonl"
        items = read_jsonl(path)
        updated = [replacement if item.get("id") == record_id else item for item in items]
        if not any(item.get("id") == record_id for item in items):
            updated.append(replacement)
        text = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in updated)
        atomic_text(path, text)

    def add_repo(self, name: str, commit: str, url: str | None = None, local: Path | None = None, related_papers: list[str] | None = None, tags: list[str] | None = None, notes: str = "") -> str:
        if not url and not local:
            raise ResearchFlowError("Repository evidence needs --url or --local.")
        local_text = None
        if local:
            resolved = local.expanduser().resolve()
            if not resolved.is_dir():
                raise ResearchFlowError(f"Repository evidence local path does not exist: {resolved}")
            local_text = str(resolved)
        record_id = allocate_id(research_home(), "REPO")
        metadata = {
            "id": record_id, "name": name, "source": {"url": url, "local": local_text},
            "pin": {"commit": commit}, "retrieved_at": utc_now(),
            "related_papers": related_papers or [], "important_paths": [],
            "tags": tags or [], "notes": notes,
        }
        validate_record("repository_evidence", metadata)
        write_yaml(self.project.root / "evidence" / "repos" / "manifests" / f"{record_id}.yaml", metadata)
        return record_id

    def show(self, record_id: str) -> dict[str, Any]:
        prefix = record_id.split("-", 1)[0]
        if prefix == "PAPER":
            path = self.project.root / "evidence" / "papers" / "analysis" / f"{record_id}.md"
            if not path.exists():
                raise ResearchFlowError(f"Paper evidence not found: {record_id}")
            metadata, body = read_markdown_record(path)
            from .review import paper_verification
            return {"metadata": metadata, "body": body, "verification_status": paper_verification(metadata)}
        if prefix == "REPO":
            path = self.project.root / "evidence" / "repos" / "manifests" / f"{record_id}.yaml"
            return read_yaml(path)
        raise ResearchFlowError(f"Unsupported evidence ID: {record_id}")

    def list(self, kind: str) -> list[dict[str, Any]]:
        if kind == "paper":
            return read_jsonl(self.project.root / "evidence" / "papers" / "index.jsonl")
        if kind == "repo":
            return [read_yaml(path) for path in sorted((self.project.root / "evidence" / "repos" / "manifests").glob("REPO-*.yaml"))]
        raise ResearchFlowError(f"Unknown evidence kind: {kind}")

    def search(self, query: str, kind: str | None = None) -> list[dict[str, Any]]:
        terms = query.casefold().split()
        candidates: list[dict[str, Any]] = []
        if kind in (None, "paper"):
            candidates.extend({"kind": "paper", **item} for item in self.list("paper"))
        if kind in (None, "repo"):
            candidates.extend({"kind": "repo", **item} for item in self.list("repo"))
        return [item for item in candidates if all(term in str(item).casefold() for term in terms)]
