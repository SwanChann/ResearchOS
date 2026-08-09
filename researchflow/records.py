from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import research_home
from .errors import ResearchFlowError
from .ids import allocate_id
from .io import atomic_text, markdown_record, read_markdown_record, utc_now
from .project import ResearchProject
from .schema import validate_record

SECTIONS = {
    "observation": "## Observation\n\n{content}\n\n## Evidence\n\n{evidence_text}\n\n## Boundary\n\nNot yet specified.\n\n## Possible Explanations\n\nNeeds verification; an observation does not establish causality.",
    "hypothesis": "## Hypothesis\n\n{content}\n\n## Why It May Be True\n\nNeeds evidence.\n\n## Evidence For\n\n{evidence_text}\n\n## Evidence Against\n\nNot yet recorded.\n\n## Falsification Condition\n\n{falsification}\n\n## Proposed Experiment\n\nNot yet designed.",
    "decision": "## Decision\n\n{content}\n\n## Why\n\n{reason}\n\n## Evidence\n\n{evidence_text}\n\n## Alternatives Considered\n\nNot yet recorded.\n\n## Revisit When\n\nNew evidence materially changes the decision basis.",
}


def _require_refs(project: ResearchProject, refs: list[str]) -> None:
    locations = {
        "OBS": project.root / "memory" / "observations",
        "HYP": project.root / "memory" / "hypotheses",
        "DEC": project.root / "memory" / "decisions",
        "EXP": project.root / "experiments" / "cards",
        "PAPER": project.root / "evidence" / "papers" / "analysis",
        "REPO": project.root / "evidence" / "repos" / "manifests",
        "RUN": project.root / "runs",
    }
    for ref in refs:
        prefix = ref.split("-", 1)[0]
        folder = locations.get(prefix)
        if folder is None:
            raise ResearchFlowError(f"Unsupported evidence reference: {ref}")
        matches = list(folder.glob(f"{ref}.*")) if prefix != "RUN" else [folder / ref / "run.yaml"]
        if not any(path.exists() for path in matches):
            raise ResearchFlowError(f"Broken evidence reference {ref}: no matching record in project {project.data['id']}")


def add_observation(project: ResearchProject, title: str, content: str, refs: list[str] | None = None, confidence: str = "medium", observation_type: str = "project_observation") -> str:
    refs = refs or []
    _require_refs(project, refs)
    record_id = allocate_id(research_home(), "OBS")
    metadata = {"id": record_id, "created": utc_now(), "type": observation_type, "title": title, "evidence": {"refs": refs}, "confidence": confidence}
    validate_record("observation", metadata)
    body = SECTIONS["observation"].format(content=content, evidence_text="\n".join(f"- {ref}" for ref in refs) or "No linked evidence yet.")
    atomic_text(project.root / "memory" / "observations" / f"{record_id}.md", markdown_record(metadata, body))
    return record_id


def add_hypothesis(project: ResearchProject, title: str, statement: str, observations: list[str] | None = None, papers: list[str] | None = None, falsification: str = "Not yet specified.") -> str:
    observations, papers = observations or [], papers or []
    _require_refs(project, observations + papers)
    record_id = allocate_id(research_home(), "HYP")
    now = utc_now()
    metadata = {"id": record_id, "status": "proposed", "based_on": {"observations": observations, "papers": papers}, "created": now, "updated": now, "title": title}
    validate_record("hypothesis", metadata)
    refs = observations + papers
    body = SECTIONS["hypothesis"].format(content=statement, evidence_text="\n".join(f"- {ref}" for ref in refs) or "No linked evidence yet.", falsification=falsification)
    atomic_text(project.root / "memory" / "hypotheses" / f"{record_id}.md", markdown_record(metadata, body))
    return record_id


def add_decision(project: ResearchProject, decision: str, reason: str, refs: list[str]) -> str:
    _require_refs(project, refs)
    record_id = allocate_id(research_home(), "DEC")
    metadata = {"id": record_id, "decision": decision, "based_on": refs, "created": utc_now()}
    validate_record("decision", metadata)
    body = SECTIONS["decision"].format(content=decision, reason=reason, evidence_text="\n".join(f"- {ref}" for ref in refs))
    atomic_text(project.root / "memory" / "decisions" / f"{record_id}.md", markdown_record(metadata, body))
    return record_id


def show_record(project: ResearchProject, record_id: str) -> tuple[dict[str, Any], str]:
    folders = {"OBS": "observations", "HYP": "hypotheses", "DEC": "decisions"}
    prefix = record_id.split("-", 1)[0]
    if prefix not in folders:
        raise ResearchFlowError(f"Unsupported memory record ID: {record_id}")
    path = project.root / "memory" / folders[prefix] / f"{record_id}.md"
    if not path.exists():
        raise ResearchFlowError(f"Memory record not found: {record_id}")
    return read_markdown_record(path)
