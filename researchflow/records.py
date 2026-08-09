from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import research_home
from .errors import ResearchFlowError
from .ids import allocate_id
from .io import atomic_text, markdown_record, read_markdown_record, utc_now
from .project import ResearchProject, update_current_state
from .schema import validate_record

SECTIONS = {
    "observation": "## Observation\n\n{content}\n\n## Evidence\n\n{evidence_text}\n\n## Boundary\n\nNot yet specified.\n\n## Possible Explanations\n\nNeeds verification; an observation does not establish causality.",
    "hypothesis": "## Hypothesis\n\n{content}\n\n## Why It May Be True\n\nNeeds evidence.\n\n## Evidence For\n\n{evidence_text}\n\n## Evidence Against\n\nNot yet recorded.\n\n## Falsification Condition\n\n{falsification}\n\n## Proposed Experiment\n\nNot yet designed.",
    "decision": "## Decision\n\n{content}\n\n## Why\n\n{reason}\n\n## Evidence\n\n{evidence_text}\n\n## Alternatives Considered\n\nNot yet recorded.\n\n## Revisit When\n\nNew evidence materially changes the decision basis.",
}


def record_exists(project: ResearchProject, ref: str) -> bool:
    locations = {
        "OBS": project.root / "memory" / "observations",
        "HYP": project.root / "memory" / "hypotheses",
        "DEC": project.root / "memory" / "decisions",
        "EXP": project.root / "experiments" / "cards",
        "PAPER": project.root / "evidence" / "papers" / "analysis",
        "REPO": project.root / "evidence" / "repos" / "manifests",
        "RUN": project.root / "runs",
    }
    prefix = ref.split("-", 1)[0]
    folder = locations.get(prefix)
    if folder is None:
        return False
    matches = list(folder.glob(f"{ref}.*")) if prefix != "RUN" else [folder / ref / "run.yaml"]
    return any(path.exists() for path in matches)


def _require_refs(project: ResearchProject, refs: list[str]) -> None:
    for ref in refs:
        if not record_exists(project, ref):
            raise ResearchFlowError(f"Broken evidence reference {ref}: no matching record in project {project.data['id']}")


def broken_references(project: ResearchProject) -> list[str]:
    refs: list[tuple[str, str]] = []
    for folder in ("observations", "hypotheses", "decisions"):
        for path in (project.root / "memory" / folder).glob("*.md"):
            metadata, _ = read_markdown_record(path)
            if folder == "observations":
                values = metadata.get("evidence", {}).get("refs", [])
            elif folder == "hypotheses":
                based = metadata.get("based_on", {})
                values = based.get("observations", []) + based.get("papers", [])
            else:
                values = metadata.get("based_on", [])
            refs.extend((path.name, value) for value in values)
    for path in (project.root / "experiments" / "cards").glob("*.yaml"):
        data = __import__("yaml").safe_load(path.read_text(encoding="utf-8")) or {}
        values = [data.get("hypothesis", {}).get("id")]
        evidence = data.get("evidence", {})
        values += evidence.get("papers", []) + evidence.get("repos", []) + evidence.get("observations", [])
        refs.extend((path.name, value) for value in values if value)
    for path in (project.root / "runs").glob("RUN-*/run.yaml"):
        data = __import__("yaml").safe_load(path.read_text(encoding="utf-8")) or {}
        if data.get("experiment"):
            refs.append((path.parent.name, data["experiment"]))
    return [f"{source} -> {ref}" for source, ref in refs if not record_exists(project, ref)]


def add_observation(project: ResearchProject, title: str, content: str, refs: list[str] | None = None, confidence: str = "medium", observation_type: str = "project_observation") -> str:
    refs = refs or []
    _require_refs(project, refs)
    record_id = allocate_id(research_home(), "OBS")
    metadata = {"id": record_id, "created": utc_now(), "type": observation_type, "title": title, "evidence": {"refs": refs}, "confidence": confidence}
    validate_record("observation", metadata)
    body = SECTIONS["observation"].format(content=content, evidence_text="\n".join(f"- {ref}" for ref in refs) or "No linked evidence yet.")
    atomic_text(project.root / "memory" / "observations" / f"{record_id}.md", markdown_record(metadata, body))
    update_current_state(project, "Next Action", f"Review {record_id} and decide whether it warrants a hypothesis or decision.")
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
    update_current_state(project, "Active Hypothesis", f"{record_id} · proposed")
    update_current_state(project, "Current Stage", "Hypothesis proposed; experiment not yet designed.")
    update_current_state(project, "Next Action", f"Design the smallest falsifiable experiment for {record_id}.")
    return record_id


def add_decision(project: ResearchProject, decision: str, reason: str, refs: list[str]) -> str:
    _require_refs(project, refs)
    record_id = allocate_id(research_home(), "DEC")
    metadata = {"id": record_id, "decision": decision, "based_on": refs, "created": utc_now()}
    validate_record("decision", metadata)
    body = SECTIONS["decision"].format(content=decision, reason=reason, evidence_text="\n".join(f"- {ref}" for ref in refs))
    atomic_text(project.root / "memory" / "decisions" / f"{record_id}.md", markdown_record(metadata, body))
    update_current_state(project, "Current Stage", f"Decision recorded: {record_id}.")
    update_current_state(project, "Next Action", "Execute the decision or revisit it only when its stated evidence boundary changes.")
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
