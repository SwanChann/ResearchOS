from __future__ import annotations

import subprocess
from datetime import date, datetime

from .io import atomic_text, read_jsonl
from .project import ResearchProject, parse_current_state


def _modified_on(path, day: date) -> bool:
    return datetime.fromtimestamp(path.stat().st_mtime).date() == day


def _event_on(item: dict, day: date) -> bool:
    value = item.get("at")
    if not isinstance(value, str):
        return False
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone()
    return timestamp.date() == day


def _as_markdown(value: str | None, fallback: str) -> str:
    text = (value or "").strip()
    if not text:
        return f"- {fallback}"
    if text.startswith("-"):
        return text
    return f"- {text}"


def create_daily_log(project: ResearchProject, day: date | None = None) -> str:
    day = day or date.today()
    target = project.root / "notes" / "daily" / f"{day.isoformat()}.md"
    changed = []
    if (project.repo / ".git").exists():
        result = subprocess.run(["git", "-C", str(project.repo), "status", "--short"], capture_output=True, text=True)
        changed = [line for line in result.stdout.splitlines() if line.strip()]
    categories = {
        "observations": (project.root / "memory" / "observations", "OBS-*.md"),
        "hypotheses": (project.root / "memory" / "hypotheses", "HYP-*.md"),
        "decisions": (project.root / "memory" / "decisions", "DEC-*.md"),
    }
    recent: dict[str, list[str]] = {}
    for name, (folder, pattern) in categories.items():
        recent[name] = sorted(
            path.stem for path in folder.glob(pattern)
            if path.is_file() and _modified_on(path, day)
        )
    run_events = read_jsonl(project.root / "runs" / "registry.jsonl")
    recent["runs"] = sorted({
        item["id"] for item in run_events
        if item.get("event") == "registered"
        and isinstance(item.get("id"), str)
        and _event_on(item, day)
    })
    state = parse_current_state(project.root / "memory" / "current-state.md")
    blockers = _as_markdown(state.get("Open Blockers"), "None recorded.")
    next_action = _as_markdown(state.get("Next Action"), "No next action recorded.")
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

{blockers}

## Next Actions

{next_action}
"""
    atomic_text(target, text)
    return str(target)
