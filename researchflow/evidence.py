from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config import research_home
from .errors import ResearchFlowError
from .ids import allocate_id
from .io import append_jsonl, atomic_text, markdown_record, read_jsonl, read_markdown_record, read_yaml, utc_now, write_yaml
from .project import ResearchProject
from .schema import validate_record

PAPER_BODY = """# {title}

## TL;DR

Needs verification.

## Problem

## Core Method

## Architecture

## Training

## Evaluation

## Key Results

## Limitations

## Relevance to Project

## Verified Claims

No claims verified yet.

## Open Questions
"""


class EvidenceStore:
    def __init__(self, project: ResearchProject):
        self.project = project

    def add_paper(self, pdf: Path, title: str, authors: list[str] | None = None, venue: str | None = None, year: int | None = None, url: str | None = None, tags: list[str] | None = None) -> str:
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
            "tags": tags or [], "status": "unread", "core_operator": None,
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
            return {"metadata": metadata, "body": body}
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

