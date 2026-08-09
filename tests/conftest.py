from __future__ import annotations

from pathlib import Path

import pytest

from researchflow.config import init_config


@pytest.fixture
def rf_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    config = tmp_path / "config.yaml"
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("RESEARCHFLOW_CONFIG", str(config))
    init_config(home, config)
    return {"config": config, "home": home, "repo": repo}

