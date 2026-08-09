from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import config_path, load_config, research_home
from .errors import ResearchFlowError
from .project import ResearchProject, list_projects
from .schema import schema_dir, validate_record
from .io import read_yaml


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
            result = subprocess.run(["git", "-C", str(project.repo), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
            checks.append(Check(f"project {candidate} Git", result.returncode == 0, result.stderr.strip() or result.stdout.strip()))
        for path in project.root.rglob("*"):
            match = re.search(r"(?:PAPER|REPO|OBS|HYP|EXP|RUN|DEC)-\d+", path.name)
            if match:
                ids.append(match.group())
        for card in (project.root / "experiments" / "cards").glob("EXP-*.yaml"):
            try:
                validate_record("experiment", read_yaml(card))
                checks.append(Check(f"card {card.stem}", True, "valid"))
            except ResearchFlowError as exc:
                checks.append(Check(f"card {card.stem}", False, str(exc)))
    duplicates = sorted({value for value in ids if ids.count(value) > 1 and not value.startswith("RUN-")})
    checks.append(Check("duplicate record IDs", not duplicates, ", ".join(duplicates) if duplicates else "none"))
    # GPU availability is reported by compute probe; doctor only verifies configured machine shape.
    invalid_machines = [name for name, value in config.get("machines", {}).items() if not isinstance(value, dict) or "type" not in value]
    checks.append(Check("machine config", not invalid_machines, ", ".join(invalid_machines) if invalid_machines else "valid"))
    return checks

