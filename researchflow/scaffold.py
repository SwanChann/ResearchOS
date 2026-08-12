from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import ResearchFlowError
from .evidence import DEEP_READ_BODY, EvidenceStore
from .io import atomic_text, markdown_record, read_markdown_record, write_yaml
from .literature import LiteratureMatrixStore
from .schema import validate_record


def _new_target(path: Path) -> Path:
    target = path.expanduser().resolve()
    if target.exists():
        raise ResearchFlowError(f"Scaffold target already exists: {target}")
    return target


def paper_analysis_scaffold(project, paper_id: str, output: Path) -> Path:
    target = _new_target(output)
    source = project.root / "evidence" / "papers" / "analysis" / f"{paper_id}.md"
    if not source.is_file():
        raise ResearchFlowError(f"Paper evidence not found: {paper_id}")
    metadata, _ = read_markdown_record(source)
    atomic_text(target, markdown_record(metadata, DEEP_READ_BODY.format(title=metadata["title"])))
    return target


def matrix_entry_scaffold(project, paper_id: str, output: Path) -> Path:
    target = _new_target(output)
    matrix = LiteratureMatrixStore(project).load()
    project.evidence.show(paper_id)
    write_yaml(target, {
        "paper_id": paper_id,
        "role": "Agent-generated draft; requires human review.",
        "decision": "supporting",
        "next_checks": ["Review every cell against the locked source fingerprint."],
        "cells": {
            axis["id"]: {
                "status": "not_reported",
                "text": "Agent-generated draft; determine explicitly from the verified source.",
                "evidence": [],
            } for axis in matrix["axes"]
        },
    })
    return target


def synthesis_idea_scaffold(project, output: Path) -> Path:
    target = _new_target(output)
    matrix = LiteratureMatrixStore(project).load()
    atomic_text(target, "# Agent-generated draft. Fill evidence refs and run rf preflight matrix-synthesis before writing.\n" + __import__("yaml").safe_dump({
        "matrix_id": matrix["id"], "mode": "upsert",
        "syntheses": [{
            "id": "SYN-001", "statement": "DRAFT", "strength": "analyst_inference",
            "evidence": [], "caveat": "DRAFT; requires human semantic review.",
        }],
        "ideas": [{
            "id": "XIDEA-001", "title": "DRAFT", "trigger": "DRAFT", "mechanism": "DRAFT",
            "falsification": "DRAFT", "risks": "DRAFT", "novelty": "unchecked", "evidence": [],
        }],
    }, sort_keys=False, allow_unicode=True))
    return target


def artifact_scaffold(output: Path, artifact_path: Path, title: str, artifact_type: str) -> Path:
    target = _new_target(output)
    write_yaml(target, {
        "agent_generated_draft": True,
        "path": str(artifact_path), "title": title, "type": artifact_type,
        "status": "draft", "authority": "researchflow_workspace",
        "derived_from": [], "evidence": [], "schema": None, "version": None,
    })
    return target


def preflight(project, kind: str, path: Path) -> dict[str, Any]:
    source = path.expanduser().resolve()
    if kind == "paper-analysis":
        metadata, body = read_markdown_record(source)
        validate_record("paper", metadata)
        EvidenceStore._validate_deep_read(body)
        return {
            "valid": True, "kind": kind,
            "meaning": "Paper analysis contract passes; interpretation, reproduction, and scientific claims remain unestablished.",
        }
    if kind == "matrix-entry":
        return LiteratureMatrixStore(project).preflight_entry_file(source)
    if kind == "matrix-synthesis":
        return LiteratureMatrixStore(project).preflight_synthesis_file(source)
    if kind == "artifact":
        return __import__("researchflow.artifact", fromlist=["ArtifactStore"]).ArtifactStore(project).preflight_request(source)
    raise ResearchFlowError(f"Unknown scaffold preflight kind: {kind}")
