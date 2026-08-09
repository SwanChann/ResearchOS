from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .errors import ResearchFlowError
from .io import read_yaml, write_yaml


def config_path() -> Path:
    override = os.environ.get("RESEARCHFLOW_CONFIG")
    return Path(override).expanduser().resolve() if override else Path.home() / ".researchflow" / "config.yaml"


def init_config(research_home: Path, path: Path | None = None, force: bool = False) -> Path:
    target = path or config_path()
    if target.exists() and not force:
        raise ResearchFlowError(f"ResearchFlow is already initialized at {target}. Use --force to replace only this config.")
    research_home = research_home.expanduser().resolve()
    research_home.mkdir(parents=True, exist_ok=True)
    (research_home / ".projects").mkdir(exist_ok=True)
    write_yaml(target, {
        "schema_version": 1,
        "research_home": str(research_home),
        "default_project": None,
        "machines": {},
        "preferences": {},
    })
    return target


def load_config(path: Path | None = None) -> dict[str, Any]:
    target = path or config_path()
    if not target.exists():
        raise ResearchFlowError(f"ResearchFlow is not initialized. Run: rf init --home <path>\nMissing: {target}")
    data = read_yaml(target)
    if data.get("schema_version") != 1 or not data.get("research_home"):
        raise ResearchFlowError(f"Invalid ResearchFlow config: {target}. Expected schema_version: 1 and research_home.")
    return data


def save_config(data: dict[str, Any], path: Path | None = None) -> None:
    write_yaml(path or config_path(), data)


def research_home(config: dict[str, Any] | None = None) -> Path:
    return Path((config or load_config())["research_home"]).expanduser().resolve()

