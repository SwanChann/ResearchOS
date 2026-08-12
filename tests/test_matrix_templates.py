from pathlib import Path

import pytest

from researchflow.errors import ResearchFlowError
from researchflow.io import markdown_record, read_markdown_record, write_yaml
from researchflow.literature import (
    EMBODIED_NAVIGATION_AXES,
    GENERIC_AXES,
    LiteratureMatrixStore,
    confirm_axes,
    load_axes_file,
    scaffold_axes,
)
from researchflow.project import ResearchProject, add_project


def _verified_paper(project: ResearchProject, tmp_path: Path) -> str:
    pdf = tmp_path / "跨领域 fixture.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% TEST FIXTURE\n")
    paper_id = project.evidence.add_paper(pdf, "MLLM overthinking TEST", authors=["Fixture Author"], year=2026)
    path = project.root / "evidence" / "papers" / "analysis" / f"{paper_id}.md"
    metadata, _ = read_markdown_record(path)
    body = """# TEST deep read

## Source Snapshot
TEST fixture only.

## Claim Strength Scale
S1 direct result.

## Verified Claims
| ID | Claim | Strength | PDF page(s) |
|---|---|---|---|
| C01 | TEST claim | S1 | p. 2 |

## Critical Assessment
TEST only.

## Idea Seeds
### IDEA-01 - TEST
Smallest falsification test: TEST.
"""
    path.write_text(markdown_record(metadata, body), encoding="utf-8")
    project.evidence.verify_paper(
        paper_id,
        sha256="A" * 64,
        source_version="TEST-v1",
        page_count=2,
        core_operator="TEST operator",
        primary_logic="TEST logic",
        methods=["TEST method"],
    )
    return paper_id


def _entry(paper_id: str, axes) -> dict:
    return {
        "paper_id": paper_id,
        "role": "TEST cross-domain fixture",
        "decision": "central",
        "next_checks": ["TEST only"],
        "cells": {
            axis["id"]: {
                "status": "supported",
                "text": f"TEST {axis['id']}",
                "evidence": [{"pages": "p. 2", "claim_ids": ["C01"], "locator": "TEST table"}],
            }
            for axis in axes
        },
    }


def test_generic_and_embodied_navigation_templates_are_distinct(rf_env):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    matrix = LiteratureMatrixStore(project)
    matrix.initialize("Generic TEST", "MLLM/defect TEST fixture")
    assert [axis["id"] for axis in matrix.load()["axes"]] == [axis["id"] for axis in GENERIC_AXES]
    assert matrix.load()["axes_version"] == "generic-v1"

    matrix.path.unlink()
    matrix.initialize("Navigation TEST", "Embodied navigation TEST fixture", template="embodied-navigation")
    assert [axis["id"] for axis in matrix.load()["axes"]] == [axis["id"] for axis in EMBODIED_NAVIGATION_AXES]
    assert matrix.load()["axes_version"] == "embodied-navigation-v1"


def test_custom_axes_draft_validate_confirm_and_invalid_definitions(rf_env, tmp_path):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    axes_path = tmp_path / "自定义 axes.yaml"
    scaffold_axes(axes_path)
    assert load_axes_file(axes_path)["status"] == "draft"
    with pytest.raises(ResearchFlowError, match="confirmed"):
        LiteratureMatrixStore(project).initialize("TEST", "TEST", axes_file=axes_path)
    confirm_axes(axes_path)
    LiteratureMatrixStore(project).initialize("TEST", "TEST", axes_file=axes_path)

    invalid = tmp_path / "invalid.yaml"
    data = load_axes_file(axes_path)
    data.pop("sha256")
    data["axes"].append(dict(data["axes"][0]))
    write_yaml(invalid, data)
    with pytest.raises(ResearchFlowError, match="Duplicate axis ID"):
        load_axes_file(invalid)


def test_axes_lock_and_explicit_migration_preserve_evidence(rf_env, tmp_path):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    paper_id = _verified_paper(project, tmp_path)
    matrix = LiteratureMatrixStore(project)
    matrix.initialize("TEST", "MLLM/defect cross-domain fixture", template="embodied-navigation")
    matrix.add_entry(_entry(paper_id, EMBODIED_NAVIGATION_AXES))
    assert matrix.load()["axes_locked"] is True

    migration = tmp_path / "migration.yaml"
    write_yaml(migration, {
        "schema_version": 1,
        "matrix_id": "LITMATRIX-0001",
        "from_axes_version": "embodied-navigation-v1",
        "target": {"template": "generic"},
        "mapping": {
            "research_question": "research_question",
            "architecture": "method_architecture",
            "training_data": "data_training",
            "benchmarks": "evaluation_protocol",
            "main_results": "main_results",
            "failure_boundary": "limitations_failure_boundary",
            "relevance": "project_relevance",
            "use_as": "literature_role",
        },
    })
    before = matrix.path.read_bytes()
    preview = matrix.migrate_axes_file(migration, dry_run=True)
    assert preview["changed"] is True
    assert matrix.path.read_bytes() == before
    result = matrix.migrate_axes_file(migration)
    assert Path(result["backup_snapshot"]).exists()
    record = matrix.load()
    assert record["axes_version"] == "generic-v1"
    assert record["papers"][0]["cells"]["method_architecture"]["evidence"][0]["claim_ids"] == ["C01"]
    assert {cell["axis_id"] for cell in record["papers"][0]["superseded_cells"]} == {
        "planning_control_interface", "temporal_structure", "real_world", "deployment_dependencies"
    }
    assert matrix.migrate_axes_file(migration)["idempotent_replay"] is True


def test_legacy_matrix_remains_readable(rf_env):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    matrix = LiteratureMatrixStore(project)
    matrix.initialize("TEST", "TEST")
    record, body = read_markdown_record(matrix.path)
    for key in ("axes_version", "axes_source", "axes_locked", "axes_migrations"):
        record.pop(key)
    record["schema_version"] = 1
    matrix.path.write_text(markdown_record(record, body), encoding="utf-8")
    assert matrix.validate()["axes_version"] == "legacy-embedded-v1"
