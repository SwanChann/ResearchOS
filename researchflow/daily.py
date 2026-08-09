from __future__ import annotations

import subprocess
from datetime import date

from .io import atomic_text
from .project import ResearchProject


def create_daily_log(project: ResearchProject, day: date | None = None) -> str:
    day = day or date.today()
    target = project.root / "notes" / "daily" / f"{day.isoformat()}.md"
    changed = []
    if (project.repo / ".git").exists():
        result = subprocess.run(["git", "-C", str(project.repo), "status", "--short"], capture_output=True, text=True)
        changed = [line for line in result.stdout.splitlines() if line.strip()]
    categories = {
        "observations": project.root / "memory" / "observations",
        "hypotheses": project.root / "memory" / "hypotheses",
        "decisions": project.root / "memory" / "decisions",
        "runs": project.root / "runs",
    }
    recent: dict[str, list[str]] = {}
    for name, folder in categories.items():
        recent[name] = sorted(path.stem for path in folder.glob("*") if path.is_file() and date.fromtimestamp(path.stat().st_mtime) == day)
    text = f"""# Daily Research Log — {day.isoformat()}

## Progress

- Research repo changes: {len(changed)} file(s).
- New runs: {', '.join(recent['runs']) if recent['runs'] else 'none'}.

## Key Findings

- New observations: {', '.join(recent['observations']) if recent['observations'] else 'none'}.
- New hypotheses: {', '.join(recent['hypotheses']) if recent['hypotheses'] else 'none'}.

## Decisions

- New decisions: {', '.join(recent['decisions']) if recent['decisions'] else 'none'}.

## Problems / Uncertainty

- Add only unresolved issues that can change future research judgment.

## Next Actions

- Review `memory/current-state.md` and record one decision-relevant next action.
"""
    atomic_text(target, text)
    return str(target)

