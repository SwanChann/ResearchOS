from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import config_path, load_config, research_home
from .errors import ResearchFlowError
from .project import ResearchProject, SKILL_NAMES, list_projects, parse_current_state
from .schema import schema_dir, validate_record
from .io import read_yaml
from .records import broken_references
from .compute import probe_machine
from .gitops import inspect_git_state


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    severity: str = "pass"

    @property
    def status(self) -> str:
        if not self.ok:
            return "FAIL"
        return "WARN" if self.severity == "warning" else "PASS"


REQUIRED_CURRENT_STATE_SECTIONS = {
    "Main Research Question",
    "Current Stage",
    "Active Hypothesis",
    "Active Experiment",
    "Current Best Baseline",
    "Open Blockers",
    "Next Action",
}


def run_doctor(project_id: str | None = None, probe_machines: bool = False) -> list[Check]:
    checks: list[Check] = []
    try:
        config = load_config()
        checks.append(Check("config", True, str(config_path())))
    except ResearchFlowError as exc:
        return [Check("config", False, str(exc))]
    home = research_home(config)
    checks.append(Check("research home", home.is_dir(), str(home)))
    checks.append(Check("schema version", config.get("schema_version") == 1, str(config.get("schema_version"))))
    checks.append(Check("schema files", schema_dir().is_dir(), str(schema_dir())))
    checks.append(Check("Python", sys.version_info >= (3, 10), sys.version.split()[0]))
    checks.append(Check("Git", shutil.which("git") is not None, shutil.which("git") or "not found"))
    checks.append(Check("SSH", shutil.which("ssh") is not None, shutil.which("ssh") or "not found"))
    projects = [project_id] if project_id else list_projects(config)
    ids: list[str] = []
    for candidate in projects:
        try:
            project = ResearchProject.open(candidate, config)
        except ResearchFlowError as exc:
            checks.append(Check(f"project {candidate}", False, str(exc)))
            continue
        checks.append(Check(f"project {candidate} path", project.root.is_dir(), str(project.root)))
        git_state = inspect_git_state(project.repo)
        checks.append(Check(f"project {candidate} repo reachable", git_state.reachable, str(project.repo)))
        if git_state.reachable:
            checks.append(Check(
                f"project {candidate} Git repository",
                True,
                "yes" if git_state.is_repository else (git_state.error or "no"),
                "pass" if git_state.is_repository else "warning",
            ))
        if git_state.is_repository:
            head_detail = (
                f"commit {git_state.head_commit}"
                if git_state.head_exists
                else "unborn HEAD; no commit/checkpoint exists"
            )
            checks.append(Check(
                f"project {candidate} Git HEAD/checkpoint",
                True,
                head_detail,
                "pass" if git_state.head_exists else "warning",
            ))
            branch_detail = "detached HEAD" if git_state.detached else f"branch {git_state.branch or 'unknown'}"
            checks.append(Check(
                f"project {candidate} Git branch",
                True,
                branch_detail,
                "warning" if git_state.detached else "pass",
            ))
            dirty_detail = (
                "clean"
                if git_state.clean
                else f"dirty: {git_state.tracked_modifications} tracked modification(s), {git_state.untracked_files} untracked file(s)"
            )
            checks.append(Check(
                f"project {candidate} Git worktree",
                True,
                dirty_detail,
                "pass" if git_state.clean else "warning",
            ))
        startup_files = [project.root / "AGENTS.md", project.root / "KNOWLEDGE.md", project.root / "memory" / "current-state.md"]
        missing_startup = [str(path) for path in startup_files if not path.is_file()]
        checks.append(Check(
            f"project {candidate} session startup",
            not missing_startup,
            "valid" if not missing_startup else f"missing: {', '.join(missing_startup)}",
        ))
        if not missing_startup:
            state = parse_current_state(project.root / "memory" / "current-state.md")
            missing_sections = sorted(REQUIRED_CURRENT_STATE_SECTIONS - set(state))
            checks.append(Check(
                f"project {candidate} current state contract",
                not missing_sections,
                "valid" if not missing_sections else f"missing sections: {', '.join(missing_sections)}",
            ))
        missing_skills = [name for name in SKILL_NAMES if not (project.root / "skills" / name / "SKILL.md").is_file()]
        checks.append(Check(
            f"project {candidate} skills",
            not missing_skills,
            "valid" if not missing_skills else f"missing: {', '.join(missing_skills)}",
        ))
        try:
            from .snapshot import list_snapshots
            snapshots = list_snapshots(project)
            valid_snapshots = [item for item in snapshots if item.get("valid")]
            invalid_snapshots = [item for item in snapshots if item.get("error") or item.get("valid") is False]
            checks.append(Check(
                f"project {candidate} snapshot",
                not invalid_snapshots,
                f"{len(valid_snapshots)} snapshot(s) registered in the default snapshot directory"
                if valid_snapshots and not invalid_snapshots
                else f"{len(invalid_snapshots)} invalid snapshot(s)" if invalid_snapshots
                else "none; workspace has no verified recovery copy in the default snapshot directory",
                "pass" if valid_snapshots else "warning",
            ))
        except ResearchFlowError as exc:
            checks.append(Check(f"project {candidate} snapshot", True, str(exc), "warning"))
        canonical = [
            project.root / "memory" / "problems",
            project.root / "memory" / "gaps",
            project.root / "memory" / "observations",
            project.root / "memory" / "hypotheses",
            project.root / "memory" / "claims",
            project.root / "memory" / "decisions",
            project.root / "evidence" / "papers" / "analysis",
            project.root / "evidence" / "corpora",
            project.root / "evidence" / "repos" / "manifests",
            project.root / "experiments" / "cards",
        ]
        for folder in canonical:
            ids.extend(path.stem for path in folder.glob("*") if path.is_file())
        ids.extend(path.name for path in (project.root / "runs").glob("RUN-*") if path.is_dir())
        try:
            broken = broken_references(project)
            checks.append(Check(f"project {candidate} references", not broken, "; ".join(broken) if broken else "valid"))
        except ResearchFlowError as exc:
            checks.append(Check(f"project {candidate} references", False, str(exc)))
        try:
            from .artifact import ArtifactStore
            artifact_result = ArtifactStore(project).verify()
            checks.append(Check(
                f"project {candidate} artifacts",
                artifact_result["valid"],
                f"{len(artifact_result['results'])} registered; file integrity and references only"
                if artifact_result["valid"] else "hash, path, or reference mismatch",
            ))
        except ResearchFlowError as exc:
            checks.append(Check(f"project {candidate} artifacts", False, str(exc)))
        try:
            from .knowledge import KnowledgeStore
            navigation = KnowledgeStore(project).check()
            if navigation["broken_links"]:
                checks.append(Check(f"project {candidate} knowledge navigation", False, f"broken links: {', '.join(navigation['broken_links'])}"))
            else:
                checks.append(Check(
                    f"project {candidate} knowledge navigation",
                    True,
                    "current" if navigation["valid"] else "missing or stale generated region; run rf knowledge rebuild --dry-run",
                    "pass" if navigation["valid"] else "warning",
                ))
        except ResearchFlowError as exc:
            checks.append(Check(f"project {candidate} knowledge navigation", False, str(exc)))
        for card in (project.root / "experiments" / "cards").glob("EXP-*.yaml"):
            try:
                validate_record("experiment", read_yaml(card))
                checks.append(Check(f"card {card.stem}", True, "valid"))
            except ResearchFlowError as exc:
                checks.append(Check(f"card {card.stem}", False, str(exc)))
        matrix_path = project.root / ".research" / "literature_matrix.md"
        if matrix_path.exists():
            try:
                from .literature import LiteratureMatrixStore
                summary = LiteratureMatrixStore(project).validate()
                checks.append(Check(
                    f"project {candidate} literature matrix",
                    True,
                    f"{summary['papers']} papers x {summary['axes']} axes",
                ))
            except ResearchFlowError as exc:
                checks.append(Check(f"project {candidate} literature matrix", False, str(exc)))
        try:
            from .corpus_gap import CorpusStore, GapStore
            corpora = CorpusStore(project)
            corpus_values = corpora.list()
            corpus_issues = []
            for corpus in corpus_values:
                verification = corpora.verify(corpus["id"])
                corpus_issues.extend(f"{corpus['id']}: {issue}" for issue in verification["issues"])
                extraction = corpora.extraction_status(corpus["id"])
                for item in extraction["extractions"]:
                    if item["status"] not in {"missing", "accepted"} or (item["status"] == "accepted" and not item["current"]):
                        corpus_issues.append(f"{corpus['id']}/{item['paper_id']}: extraction {item['status']} or stale")
            gap_issues = []
            for gap in GapStore(project).list():
                shown = GapStore(project).show(gap["id"])
                if not shown["content_current"]:
                    gap_issues.append(f"{gap['id']}: candidate fingerprint stale")
                if gap["state"] == "approved" and not shown["approved"]:
                    gap_issues.append(f"{gap['id']}: approval stale")
            issues = [*corpus_issues, *gap_issues]
            checks.append(Check(
                f"project {candidate} corpus gap",
                not issues,
                f"{len(corpus_values)} Corpus record(s), {len(GapStore(project).list())} Gap record(s)"
                if not issues else "; ".join(issues),
                "pass" if corpus_values or GapStore(project).list() else "warning",
            ))
        except ResearchFlowError as exc:
            checks.append(Check(f"project {candidate} corpus gap", False, str(exc)))
        try:
            from .evidence_graph import EvidenceGraphStore
            graph = EvidenceGraphStore(project).check()
            if not graph["initialized"]:
                checks.append(Check(
                    f"project {candidate} evidence graph",
                    True,
                    "not initialized; legacy project remains readable and no migration was performed",
                    "warning",
                ))
            else:
                detail = f"{graph['edges']} edge(s); deterministic structure valid"
                if not graph["index"]["exists"]:
                    detail += "; derived index missing"
                elif not graph["index"]["current"]:
                    detail += "; derived index stale"
                if graph["claims"] and not graph["ready"]:
                    detail += "; one or more Claims await complete evidence or semantic review"
                checks.append(Check(
                    f"project {candidate} evidence graph",
                    graph["valid"],
                    detail if graph["valid"] else "; ".join(graph["issues"]),
                    "pass" if (graph["ready"] or not graph["claims"]) and graph["index"]["current"] else "warning",
                ))
        except ResearchFlowError as exc:
            checks.append(Check(f"project {candidate} evidence graph", False, str(exc)))
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    checks.append(Check("duplicate record IDs", not duplicates, ", ".join(duplicates) if duplicates else "none"))
    # GPU availability is reported by compute probe; doctor only verifies configured machine shape.
    invalid_machines = [name for name, value in config.get("machines", {}).items() if not isinstance(value, dict) or "type" not in value]
    checks.append(Check("machine config", not invalid_machines, ", ".join(invalid_machines) if invalid_machines else "valid"))
    for name in config.get("machines", {}):
        if name in invalid_machines:
            continue
        if not probe_machines:
            checks.append(Check(f"machine {name} live probe", True, "skipped; use --probe-machines with current authorization"))
            continue
        try:
            probe = probe_machine(name)
            gpu = probe.get("gpu") or probe.get("stdout") or "no GPU reported"
            checks.append(Check(f"machine {name} connectivity/GPU", bool(probe.get("reachable")), str(gpu)))
        except (ResearchFlowError, OSError) as exc:
            checks.append(Check(f"machine {name} connectivity/GPU", False, str(exc)))
    return checks
