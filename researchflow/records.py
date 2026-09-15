from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json

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
        "ARTIFACT": project.root / ".research",
        "PROB": project.root / "memory" / "problems",
        "GAP": project.root / "memory" / "gaps",
        "CLAIM": project.root / "memory" / "claims",
        "CORPUS": project.root / "evidence" / "corpora",
    }
    prefix = ref.split("-", 1)[0]
    if prefix == "XIDEA":
        matrix_path = project.root / ".research" / "literature_matrix.md"
        if not matrix_path.exists():
            return False
        from .literature import LiteratureMatrixStore
        return any(item["id"] == ref for item in LiteratureMatrixStore(project).load()["ideas"])
    if prefix == "CGAPRUN":
        return (project.root / ".research" / "corpus-gap" / "runs" / ref / "manifest.yaml").is_file()
    if prefix == "EGAUDIT":
        return (project.root / ".research" / "evidence-graph" / "audits" / f"{ref}.yaml").is_file()
    if prefix == "PADJ":
        try:
            from .adjacency import PaperAdjacencyStore
            PaperAdjacencyStore(project).show(ref)
            return True
        except ResearchFlowError:
            return False
    folder = locations.get(prefix)
    if folder is None:
        return False
    if prefix == "ARTIFACT":
        from .artifact import ArtifactStore
        return any(item["id"] == ref for item in ArtifactStore(project).list())
    if prefix == "CORPUS":
        return (folder / f"{ref}.yaml").is_file()
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
                values = based.get("observations", []) + based.get("papers", []) + based.get("ideas", []) + based.get("gaps", [])
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
    for path in (project.root / "memory" / "problems").glob("PROB-*.md"):
        metadata, _ = read_markdown_record(path)
        if metadata.get("supersedes"):
            refs.append((path.name, metadata["supersedes"]))
    for path in (project.root / "memory" / "claims").glob("CLAIM-*.md"):
        metadata, _ = read_markdown_record(path)
        values = [*metadata.get("supporting_findings", []), *metadata.get("counter_findings", [])]
        values.extend(item.get("run_id") for item in metadata.get("metric_evidence", []))
        values.extend(item.get("artifact_id") for item in metadata.get("metric_evidence", []))
        if metadata.get("supersedes"):
            values.append(metadata["supersedes"])
        refs.extend((path.name, value) for value in values if value)
    for path in (project.root / "memory" / "gaps").glob("GAP-*.md"):
        metadata, _ = read_markdown_record(path)
        values = [metadata.get("problem_id")]
        derivation = metadata.get("derivation", {})
        values.extend([derivation.get("corpus_id"), derivation.get("cgap_run_id")])
        values.extend(derivation.get("adjacency_ids", []))
        values.extend(item.get("ref") for item in metadata.get("known_counterevidence", []))
        if metadata.get("supersedes"):
            values.append(metadata["supersedes"])
        refs.extend((path.name, value) for value in values if value)
    for path in (project.root / "evidence" / "corpora").glob("CORPUS-*.yaml"):
        metadata = __import__("yaml").safe_load(path.read_text(encoding="utf-8")) or {}
        values = [item.get("id") for item in metadata.get("papers", [])]
        if metadata.get("supersedes"):
            values.append(metadata["supersedes"])
        refs.extend((path.name, value) for value in values if value)
    for path in (project.root / "evidence" / "corpus-extractions").glob("CORPUS-*/*.yaml"):
        metadata = __import__("yaml").safe_load(path.read_text(encoding="utf-8")) or {}
        refs.extend((path.name, value) for value in (metadata.get("corpus_id"), metadata.get("paper_id")) if value)
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


def add_hypothesis(project: ResearchProject, title: str, statement: str, observations: list[str] | None = None, papers: list[str] | None = None, falsification: str = "Not yet specified.", ideas: list[str] | None = None, gaps: list[str] | None = None) -> str:
    observations, papers, ideas, gaps = observations or [], papers or [], ideas or [], gaps or []
    _require_refs(project, observations + papers + ideas + gaps)
    idea_sources = _idea_sources(project, ideas)
    gap_sources = _gap_sources(project, gaps)
    record_id = allocate_id(research_home(), "HYP")
    now = utc_now()
    if observations and (papers or ideas):
        derivation = "mixed"
    elif observations:
        derivation = "local-observation-derived"
    else:
        derivation = "literature-derived"
    warnings = []
    if any(item["novelty"] == "unchecked" for item in idea_sources):
        warnings.append("Referenced literature idea has novelty: unchecked; novelty search/review is still required.")
    if ideas and not observations:
        warnings.append("Literature-derived hypothesis: local empirical support has not been established.")
    metadata = {
        "id": record_id, "status": "proposed",
        "based_on": {"observations": observations, "papers": papers, "ideas": ideas, "gaps": gaps},
        "provenance": {
            "derivation": derivation, "local_empirical_support": bool(observations),
            "idea_sources": idea_sources, "gap_sources": gap_sources, "warnings": warnings,
        },
        "created": now, "updated": now, "title": title,
    }
    validate_record("hypothesis", metadata)
    refs = observations + papers + ideas + gaps
    body = SECTIONS["hypothesis"].format(content=statement, evidence_text="\n".join(f"- {ref}" for ref in refs) or "No linked evidence yet.", falsification=falsification)
    atomic_text(project.root / "memory" / "hypotheses" / f"{record_id}.md", markdown_record(metadata, body))
    update_current_state(project, "Active Hypothesis", f"{record_id} · proposed")
    update_current_state(project, "Current Stage", "Hypothesis proposed; experiment not yet designed.")
    update_current_state(project, "Next Action", f"Design the smallest falsifiable experiment for {record_id}.")
    return record_id


def _idea_fingerprint(idea: dict[str, Any]) -> str:
    payload = json.dumps(idea, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _idea_sources(project: ResearchProject, ideas: list[str]) -> list[dict[str, Any]]:
    if not ideas:
        return []
    from .literature import LiteratureMatrixStore
    from .review import matrix_fingerprint
    matrix = LiteratureMatrixStore(project).load()
    by_id = {item["id"]: item for item in matrix["ideas"]}
    sources = []
    for idea_id in ideas:
        if idea_id not in by_id:
            raise ResearchFlowError(f"Idea {idea_id} is not present in the current project's formal literature matrix.")
        idea = by_id[idea_id]
        sources.append({
            "id": idea_id, "matrix_id": matrix["id"], "matrix_fingerprint": matrix_fingerprint(matrix),
            "idea_fingerprint": _idea_fingerprint(idea), "novelty": idea["novelty"],
            "evidence": idea["evidence"],
        })
    return sources


def _gap_sources(project: ResearchProject, gaps: list[str]) -> list[dict[str, Any]]:
    if not gaps:
        return []
    from .corpus_gap import GapStore
    store = GapStore(project)
    sources = []
    for gap_id in gaps:
        shown = store.show(gap_id)
        if not shown["approved"]:
            raise ResearchFlowError(f"Gap {gap_id} is not currently approved by a human reviewer.")
        review = shown["record"]["review"]
        sources.append({
            "id": gap_id, "gap_fingerprint": shown["fingerprint"],
            "reviewer": review["reviewer"], "reviewed_at": review["reviewed_at"],
        })
    return sources


def hypothesis_provenance_status(project: ResearchProject, metadata: dict[str, Any]) -> dict[str, Any]:
    provenance = metadata.get("provenance")
    if not provenance:
        return {"legacy": True, "stale": False, "warnings": ["Legacy hypothesis has no structured XIDEA provenance."]}
    if not provenance["idea_sources"] and not provenance.get("gap_sources", []):
        return {"legacy": False, "stale": False, "idea_sources": [], "gap_sources": [], "warnings": provenance["warnings"]}
    from .literature import LiteratureMatrixStore
    from .review import matrix_fingerprint
    if provenance["idea_sources"]:
        matrix = LiteratureMatrixStore(project).load()
        by_id = {item["id"]: item for item in matrix["ideas"]}
        current_matrix = matrix_fingerprint(matrix)
    else:
        by_id, current_matrix = {}, ""
    statuses = []
    for source in provenance["idea_sources"]:
        idea = by_id.get(source["id"])
        missing = idea is None
        matrix_changed = source["matrix_fingerprint"] != current_matrix
        idea_changed = not missing and source["idea_fingerprint"] != _idea_fingerprint(idea)
        statuses.append({
            "id": source["id"], "missing": missing, "matrix_changed": matrix_changed,
            "idea_changed": idea_changed, "stale": missing or matrix_changed or idea_changed,
            "novelty": idea.get("novelty") if idea else source["novelty"],
        })
    gap_statuses = []
    from .corpus_gap import GapStore
    gaps = GapStore(project)
    for source in provenance.get("gap_sources", []):
        try:
            shown = gaps.show(source["id"])
            stale = not shown["approved"] or shown["fingerprint"] != source["gap_fingerprint"]
        except ResearchFlowError:
            stale = True
        gap_statuses.append({"id": source["id"], "stale": stale})
    warnings = list(provenance["warnings"])
    if any(item["stale"] for item in statuses):
        warnings.append("Idea or literature-matrix provenance changed; hypothesis requires review.")
    if any(item["stale"] for item in gap_statuses):
        warnings.append("Approved Gap provenance changed or is no longer approved; hypothesis requires review.")
    return {
        "legacy": False,
        "stale": any(item["stale"] for item in statuses) or any(item["stale"] for item in gap_statuses),
        "idea_sources": statuses, "gap_sources": gap_statuses, "warnings": warnings,
    }


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
    folders = {
        "OBS": "observations", "HYP": "hypotheses", "DEC": "decisions",
        "PROB": "problems", "GAP": "gaps", "CLAIM": "claims",
    }
    prefix = record_id.split("-", 1)[0]
    if prefix not in folders:
        raise ResearchFlowError(f"Unsupported memory record ID: {record_id}")
    path = project.root / "memory" / folders[prefix] / f"{record_id}.md"
    if not path.exists():
        raise ResearchFlowError(f"Memory record not found: {record_id}")
    return read_markdown_record(path)
