from pathlib import Path

import pytest

from researchflow.errors import ResearchFlowError
from researchflow.project import ResearchProject, add_project, list_projects


def test_project_init_creates_human_readable_workspace(rf_env):
    workspace = add_project("toy", rf_env["repo"], name="Toy Research")
    assert list_projects() == ["toy"]
    assert (workspace / "AGENTS.md").is_file()
    assert (workspace / "KNOWLEDGE.md").is_file()
    assert (workspace / "memory/current-state.md").is_file()
    assert (workspace / "policy.yaml").is_file()
    assert (workspace / "skills/retrieve-before-reason/SKILL.md").is_file()
    assert ResearchProject.open("toy").repo == rf_env["repo"]


def test_project_rejects_invalid_repo(rf_env):
    with pytest.raises(ResearchFlowError, match="does not exist"):
        add_project("bad", Path("missing"))
