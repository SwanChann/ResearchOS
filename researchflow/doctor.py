from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import config_path, load_config, research_home
from .errors import ResearchFlowError
from .project import ResearchProject, list_projects
from .schema import schema_dir, validate_record
from .io import read_yaml
from .records import broken_references
from .compute import probe_machine
from .gitops import git


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def run_doctor(project_id: str | None = None) -> list[Check]:
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
        checks.append(Check(f"project {candidate} repo", project.repo.is_dir(), str(project.repo)))
        if project.repo.is_dir() and (project.repo / ".git").exists():
            try:
                inside = git(project.repo, "rev-parse", "--is-inside-work-tree")
                checks.append(Check(f"project {candidate} Git", inside == "true", inside))
            except ResearchFlowError as exc:
                checks.append(Check(f"project {candidate} Git", False, str(exc)))
        canonical = [
            project.root / "memory" / "observations",
            project.root / "memory" / "hypotheses",
            project.root / "memory" / "decisions",
            project.root / "evidence" / "papers" / "analysis",
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
        for card in (project.root / "experiments" / "cards").glob("EXP-*.yaml"):
            try:
                validate_record("experiment", read_yaml(card))
                checks.append(Check(f"card {card.stem}", True, "valid"))
            except ResearchFlowError as exc:
                checks.append(Check(f"card {card.stem}", False, str(exc)))
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    checks.append(Check("duplicate record IDs", not duplicates, ", ".join(duplicates) if duplicates else "none"))
    # GPU availability is reported by compute probe; doctor only verifies configured machine shape.
    invalid_machines = [name for name, value in config.get("machines", {}).items() if not isinstance(value, dict) or "type" not in value]
    checks.append(Check("machine config", not invalid_machines, ", ".join(invalid_machines) if invalid_machines else "valid"))
    for name in config.get("machines", {}):
        if name in invalid_machines:
            continue
        try:
            probe = probe_machine(name)
            gpu = probe.get("gpu") or probe.get("stdout") or "no GPU reported"
            checks.append(Check(f"machine {name} connectivity/GPU", bool(probe.get("reachable")), str(gpu)))
        except (ResearchFlowError, subprocess.SubprocessError) as exc:
            checks.append(Check(f"machine {name} connectivity/GPU", False, str(exc)))
    return checks
