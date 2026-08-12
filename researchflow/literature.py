from __future__ import annotations

import re
import hashlib
import json
from pathlib import Path
from typing import Any

from .errors import ResearchFlowError
from .io import atomic_text, markdown_record, read_markdown_record, read_yaml, utc_now
from .project import ResearchProject
from .schema import validate_record


MATRIX_RELATIVE_PATH = Path(".research/literature_matrix.md")

GENERIC_AXES = (
    {"id": "research_question", "label": "Research question", "group": "framing", "description": "The question or hypothesis the paper addresses."},
    {"id": "problem_definition", "label": "Problem definition", "group": "framing", "description": "Task assumptions, inputs, outputs, and boundary conditions."},
    {"id": "method_architecture", "label": "Method / architecture", "group": "method", "description": "Core operator, architecture, or analytical procedure."},
    {"id": "data_training", "label": "Data / training", "group": "method", "description": "Data sources, supervision, preprocessing, and optimization protocol."},
    {"id": "evaluation_protocol", "label": "Evaluation protocol", "group": "evidence", "description": "Datasets, splits, baselines, metrics, and statistical protocol."},
    {"id": "main_results", "label": "Main results", "group": "evidence", "description": "Primary source-reported quantitative or qualitative results."},
    {"id": "limitations_failure_boundary", "label": "Limitations / failure boundary", "group": "evidence", "description": "Known limitations, failure cases, and untested conditions."},
    {"id": "project_relevance", "label": "Project relevance", "group": "decision", "description": "Why the paper matters to the current project question."},
    {"id": "literature_role", "label": "Literature role", "group": "decision", "description": "Central, supporting, background, counterexample, or exclusion role."},
)

EMBODIED_NAVIGATION_AXES = (
    {"id": "research_question", "label": "研究问题", "group": "framing", "description": "论文在具身导航中提出的核心问题。"},
    {"id": "architecture", "label": "核心架构", "group": "method", "description": "感知、记忆、策略和控制的主要结构。"},
    {"id": "planning_control_interface", "label": "规划-控制接口", "group": "method", "description": "高层规划如何转化为可执行控制。"},
    {"id": "temporal_structure", "label": "时序结构", "group": "method", "description": "历史、记忆、预测和动作时间尺度。"},
    {"id": "training_data", "label": "训练与数据", "group": "method", "description": "数据来源、监督形式和训练流程。"},
    {"id": "benchmarks", "label": "基准与协议", "group": "evidence", "description": "场景、划分、指标和比较协议。"},
    {"id": "main_results", "label": "主要结果", "group": "evidence", "description": "论文主文直接报告的主要结果。"},
    {"id": "real_world", "label": "实机证据", "group": "evidence", "description": "真实机器人或现实环境证据的范围。"},
    {"id": "deployment_dependencies", "label": "部署依赖", "group": "evidence", "description": "部署所需传感器、地图、算力和外部模块。"},
    {"id": "failure_boundary", "label": "失败边界", "group": "evidence", "description": "失败模式、限制和未覆盖条件。"},
    {"id": "relevance", "label": "相关性", "group": "decision", "description": "对当前具身导航研究问题的作用。"},
    {"id": "use_as", "label": "文献角色", "group": "decision", "description": "中心工作、支撑、背景、反例或排除。"},
)

# Backward-compatible import for existing callers. New matrix initialization uses
# the generic template unless a domain template is selected explicitly.
DEFAULT_AXES = EMBODIED_NAVIGATION_AXES

MATRIX_TEMPLATES = {
    "generic": {
        "schema_version": 1,
        "name": "generic",
        "version": "generic-v1",
        "description": "Cross-domain research comparison axes.",
        "status": "confirmed",
        "axes": GENERIC_AXES,
    },
    "embodied-navigation": {
        "schema_version": 1,
        "name": "embodied-navigation",
        "version": "embodied-navigation-v1",
        "description": "The historical twelve-axis embodied-navigation comparison contract.",
        "status": "confirmed",
        "axes": EMBODIED_NAVIGATION_AXES,
    },
}

GROUP_LABELS = {
    "framing": "问题框定",
    "method": "方法与系统",
    "evidence": "证据与边界",
    "decision": "综述决策",
}


def _axes_fingerprint(axes: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> str:
    payload = json.dumps(list(axes), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_axes_definition(definition: dict[str, Any], *, allow_draft: bool = True) -> dict[str, Any]:
    if definition.get("schema_version") != 1:
        raise ResearchFlowError("Axes definition requires schema_version: 1.")
    if definition.get("status") not in ({"draft", "confirmed"} if allow_draft else {"confirmed"}):
        raise ResearchFlowError("Axes status must be confirmed before matrix initialization." if not allow_draft else "Axes status must be draft or confirmed.")
    axes = definition.get("axes")
    if not isinstance(axes, list) or not axes:
        raise ResearchFlowError("Axes definition needs a non-empty axes list.")
    identifiers: list[str] = []
    normalized = []
    for index, axis in enumerate(axes, 1):
        if not isinstance(axis, dict):
            raise ResearchFlowError(f"Axis {index} must be a mapping.")
        axis_id = str(axis.get("id") or "")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", axis_id):
            raise ResearchFlowError(f"Invalid stable axis ID at position {index}: {axis_id or '<missing>'}")
        if axis_id in identifiers:
            raise ResearchFlowError(f"Duplicate axis ID: {axis_id}")
        if axis.get("group") not in GROUP_LABELS:
            raise ResearchFlowError(f"Axis {axis_id} has invalid group: {axis.get('group')}")
        for field in ("label", "description"):
            if not str(axis.get(field) or "").strip():
                raise ResearchFlowError(f"Axis {axis_id} needs a non-empty {field}.")
        identifiers.append(axis_id)
        normalized.append({
            "id": axis_id,
            "label": str(axis["label"]).strip(),
            "group": axis["group"],
            "description": str(axis["description"]).strip(),
        })
    name = str(definition.get("name") or "custom").strip()
    version = str(definition.get("version") or f"{name}-{_axes_fingerprint(normalized)[:12]}").strip()
    return {
        "schema_version": 1,
        "name": name,
        "version": version,
        "description": str(definition.get("description") or "Project-defined literature axes.").strip(),
        "status": definition["status"],
        "axes": normalized,
        "sha256": _axes_fingerprint(normalized),
    }


def axes_template(name: str) -> dict[str, Any]:
    template = MATRIX_TEMPLATES.get(name)
    if not template:
        raise ResearchFlowError(f"Unknown matrix template {name}. Available: {', '.join(sorted(MATRIX_TEMPLATES))}")
    return validate_axes_definition({**template, "axes": [dict(axis) for axis in template["axes"]]}, allow_draft=False)


def load_axes_file(path: Path, *, allow_draft: bool = True) -> dict[str, Any]:
    return validate_axes_definition(read_yaml(path.expanduser().resolve()), allow_draft=allow_draft)


def scaffold_axes(path: Path, template: str = "generic") -> Path:
    target = path.expanduser().resolve()
    if target.exists():
        raise ResearchFlowError(f"Axes scaffold target already exists: {target}")
    definition = axes_template(template)
    definition.pop("sha256", None)
    definition["name"] = "project-custom"
    definition["version"] = "project-custom-v1"
    definition["status"] = "draft"
    from .io import write_yaml
    write_yaml(target, definition)
    return target


def confirm_axes(path: Path) -> Path:
    target = path.expanduser().resolve()
    definition = load_axes_file(target, allow_draft=True)
    definition.pop("sha256", None)
    definition["status"] = "confirmed"
    from .io import write_yaml
    write_yaml(target, definition)
    return target


class LiteratureMatrixStore:
    """A structured, page-cited cross-paper matrix with a generated Markdown view."""

    def __init__(self, project: ResearchProject):
        self.project = project
        self.path = project.root / MATRIX_RELATIVE_PATH

    def initialize(
        self,
        title: str,
        scope: str,
        *,
        template: str = "generic",
        axes_file: Path | None = None,
    ) -> Path:
        if self.path.exists():
            raise ResearchFlowError(f"Literature matrix already exists: {self.path}")
        if axes_file and template != "generic":
            raise ResearchFlowError("Use either --template or --axes-file, not both.")
        definition = load_axes_file(axes_file, allow_draft=False) if axes_file else axes_template(template)
        record = {
            "schema_version": 2,
            "id": "LITMATRIX-0001",
            "title": title.strip(),
            "scope": scope.strip(),
            "status": "active",
            "citation_basis": "pdf_page",
            "axes": [dict(axis) for axis in definition["axes"]],
            "axes_version": definition["version"],
            "axes_source": {
                "kind": "file" if axes_file else "template",
                "name": str(axes_file.expanduser().resolve()) if axes_file else definition["name"],
                "sha256": definition["sha256"],
            },
            "axes_locked": False,
            "axes_migrations": [],
            "papers": [],
            "syntheses": [],
            "ideas": [],
            "updated_at": utc_now(),
        }
        if not record["title"] or not record["scope"]:
            raise ResearchFlowError("Literature matrix title and scope must be non-empty.")
        self._write(record)
        return self.path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise ResearchFlowError("Literature matrix does not exist. Run: rf evidence matrix init --title ... --scope ...")
        record, _ = read_markdown_record(self.path)
        self._validate(record)
        return record

    def validate(self) -> dict[str, Any]:
        record = self.load()
        from .review import matrix_review_status
        statuses = {"supported": 0, "not_reported": 0, "not_applicable": 0}
        for paper in record["papers"]:
            for cell in paper["cells"].values():
                statuses[cell["status"]] += 1
        return {
            "path": str(self.path),
            "matrix_id": record["id"],
            "papers": len(record["papers"]),
            "axes": len(record["axes"]),
            "axes_version": record.get("axes_version", "legacy-embedded-v1"),
            "axes_locked": record.get("axes_locked", bool(record["papers"])),
            "syntheses": len(record["syntheses"]),
            "ideas": len(record["ideas"]),
            "cell_status": statuses,
            "valid": True,
            "review_status": matrix_review_status(record),
        }

    def add_entry_file(self, entry_path: Path) -> str:
        entry = read_yaml(entry_path.expanduser().resolve())
        return self.add_entry(entry)

    def preflight_entry_file(self, entry_path: Path) -> dict[str, Any]:
        entry = read_yaml(entry_path.expanduser().resolve())
        record = self.load()
        candidate = self._candidate_with_entry(record, entry)
        self._validate(candidate)
        return {
            "valid": True,
            "paper_id": entry.get("paper_id"),
            "would_change": True,
            "meaning": "Contract and evidence-reference checks only; semantic correctness is not established.",
        }

    def add_entry(self, entry: dict[str, Any]) -> str:
        record = self.load()
        candidate = self._candidate_with_entry(record, entry)
        self._write(candidate)
        return str(entry["paper_id"])

    def _candidate_with_entry(self, record: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
        paper_id = str(entry.get("paper_id") or "")
        if not re.fullmatch(r"PAPER-[0-9]{4}", paper_id):
            raise ResearchFlowError("Matrix entry needs a PAPER-0001 style paper_id.")
        if any(item["paper_id"] == paper_id for item in record["papers"]):
            raise ResearchFlowError(f"Literature matrix already contains {paper_id}; append is idempotent and will not duplicate it.")

        paper = self.project.evidence.show(paper_id)
        metadata = paper["metadata"]
        document = metadata.get("source", {}).get("document") or {}
        if metadata.get("status") != "verified" or not document:
            raise ResearchFlowError(f"{paper_id} must pass 'rf evidence paper verify' before matrix insertion.")

        cells = entry.get("cells")
        if not isinstance(cells, dict):
            raise ResearchFlowError("Matrix entry needs a cells mapping.")
        next_checks = entry.get("next_checks") or []
        if not isinstance(next_checks, list):
            raise ResearchFlowError("Matrix entry next_checks must be a YAML list.")
        expected = {axis["id"] for axis in record["axes"]}
        actual = set(cells)
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing or extra:
            details = []
            if missing:
                details.append(f"missing axes: {', '.join(missing)}")
            if extra:
                details.append(f"unknown axes: {', '.join(extra)}")
            raise ResearchFlowError(f"Incomplete matrix entry for {paper_id}: {'; '.join(details)}")

        normalized = {
            "paper_id": paper_id,
            "citation": self._citation(metadata),
            "title": metadata["title"],
            "year": metadata.get("year"),
            "stable_id": metadata.get("source", {}).get("url") or document["version"],
            "source_version": document["version"],
            "source_sha256": document["sha256"],
            "role": str(entry.get("role") or "未分类").strip(),
            "decision": str(entry.get("decision") or "supporting"),
            "next_checks": next_checks,
            "cells": cells,
        }
        candidate = dict(record)
        candidate["papers"] = [*record["papers"], normalized]
        if record.get("schema_version") == 2:
            candidate["axes_locked"] = True
        candidate["updated_at"] = utc_now()
        return candidate

    def preflight_synthesis_file(self, synthesis_path: Path) -> dict[str, Any]:
        update = read_yaml(synthesis_path.expanduser().resolve())
        validate_record("literature_synthesis", update)
        record = self.load()
        if update["matrix_id"] != record["id"]:
            raise ResearchFlowError(f"Synthesis update targets {update['matrix_id']}, not {record['id']}.")
        for section in ("syntheses", "ideas"):
            identifiers = [item["id"] for item in update[section]]
            if len(identifiers) != len(set(identifiers)):
                raise ResearchFlowError(f"Synthesis update contains duplicate {section} IDs.")
        candidate = dict(record)
        if update["mode"] == "replace":
            candidate["syntheses"], candidate["ideas"] = update["syntheses"], update["ideas"]
        else:
            candidate["syntheses"] = self._upsert(record["syntheses"], update["syntheses"])
            candidate["ideas"] = self._upsert(record["ideas"], update["ideas"])
        self._validate(candidate)
        return {
            "valid": True, "matrix_id": record["id"],
            "syntheses": len(candidate["syntheses"]), "ideas": len(candidate["ideas"]),
            "meaning": "Contract and source-reference checks only; novelty and scientific claims remain unestablished.",
        }

    def synthesize_file(self, synthesis_path: Path) -> dict[str, Any]:
        update = read_yaml(synthesis_path.expanduser().resolve())
        validate_record("literature_synthesis", update)
        return self.synthesize(update)

    def synthesize(self, update: dict[str, Any]) -> dict[str, Any]:
        """Atomically replace or upsert evidence-linked synthesis records."""
        validate_record("literature_synthesis", update)
        record = self.load()
        if update["matrix_id"] != record["id"]:
            raise ResearchFlowError(
                f"Synthesis update targets {update['matrix_id']}, but this project contains {record['id']}."
            )
        for section in ("syntheses", "ideas"):
            identifiers = [item["id"] for item in update[section]]
            if len(identifiers) != len(set(identifiers)):
                raise ResearchFlowError(f"Synthesis update contains duplicate {section} IDs.")

        mode = update["mode"]
        if mode == "replace":
            syntheses = update["syntheses"]
            ideas = update["ideas"]
        else:
            syntheses = self._upsert(record["syntheses"], update["syntheses"])
            ideas = self._upsert(record["ideas"], update["ideas"])

        changed = syntheses != record["syntheses"] or ideas != record["ideas"]
        if changed:
            candidate = dict(record)
            candidate["syntheses"] = syntheses
            candidate["ideas"] = ideas
            candidate["updated_at"] = utc_now()
            self._write(candidate)

        return {
            "path": str(self.path),
            "matrix_id": record["id"],
            "mode": mode,
            "syntheses": len(syntheses),
            "ideas": len(ideas),
            "changed": changed,
            "valid": True,
        }

    def render(self) -> Path:
        record = self.load()
        atomic_text(self.path, markdown_record(record, self._render_body(record)))
        return self.path

    def replace(self, record: dict[str, Any]) -> Path:
        """Replace the complete matrix after an explicit migration or synthesis update."""
        record = dict(record)
        record["updated_at"] = utc_now()
        self._write(record)
        return self.path

    def migrate_axes_file(self, migration_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
        path = migration_path.expanduser().resolve()
        migration = read_yaml(path)
        if migration.get("schema_version") != 1:
            raise ResearchFlowError("Matrix axes migration requires schema_version: 1.")
        record = self.load()
        if migration.get("matrix_id") != record["id"]:
            raise ResearchFlowError(f"Migration targets {migration.get('matrix_id')}, not {record['id']}.")
        current_version = record.get("axes_version", "legacy-embedded-v1")
        target_spec = migration.get("target")
        if not isinstance(target_spec, dict) or set(target_spec) not in ({"template"}, {"axes_file"}):
            raise ResearchFlowError("Migration target must contain exactly one of: template, axes_file.")
        if "template" in target_spec:
            definition = axes_template(str(target_spec["template"]))
            source = {"kind": "template", "name": definition["name"], "sha256": definition["sha256"]}
        else:
            axes_path = (path.parent / str(target_spec["axes_file"])).resolve()
            definition = load_axes_file(axes_path, allow_draft=False)
            source = {"kind": "file", "name": str(axes_path), "sha256": definition["sha256"]}
        mapping = migration.get("mapping") or {}
        if not isinstance(mapping, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in mapping.items()):
            raise ResearchFlowError("Migration mapping must be an old_axis: new_axis mapping.")
        expected_version = migration.get("from_axes_version")
        if current_version == definition["version"]:
            replay = next((
                item for item in record.get("axes_migrations", [])
                if item.get("from_axes_version") == expected_version
                and item.get("to_axes_version") == definition["version"]
                and item.get("mapping") == mapping
            ), None)
            if replay:
                return {
                    "matrix_id": record["id"],
                    "from_axes_version": expected_version,
                    "to_axes_version": definition["version"],
                    "mapping": dict(mapping),
                    "preserved_superseded_cells": replay.get("preserved_superseded_cells", 0),
                    "new_review_placeholders": replay.get("new_review_placeholders", 0),
                    "papers": len(record["papers"]),
                    "dry_run": dry_run,
                    "changed": False,
                    "idempotent_replay": True,
                    "files": [MATRIX_RELATIVE_PATH.as_posix()],
                    "risk": "No replay change; the recorded axes migration already matches this mapping.",
                    "rollback": "No rollback is needed for this no-op replay.",
                }
        if expected_version != current_version:
            raise ResearchFlowError(
                f"Migration expects axes {expected_version}, current matrix uses {current_version}."
            )
        old_ids = {axis["id"] for axis in record["axes"]}
        new_ids = {axis["id"] for axis in definition["axes"]}
        unknown_old = sorted(set(mapping) - old_ids)
        unknown_new = sorted(set(mapping.values()) - new_ids)
        if unknown_old or unknown_new:
            raise ResearchFlowError(
                f"Migration mapping has unknown old axes: {', '.join(unknown_old) or 'none'}; "
                f"unknown new axes: {', '.join(unknown_new) or 'none'}."
            )
        if len(mapping.values()) != len(set(mapping.values())):
            raise ResearchFlowError("Migration cannot map multiple old axes onto one new axis.")
        candidate = dict(record)
        migrated_papers = []
        preserved = 0
        placeholders = 0
        for paper in record["papers"]:
            migrated = dict(paper)
            new_cells: dict[str, Any] = {}
            superseded = list(paper.get("superseded_cells", []))
            for old_id, cell in paper["cells"].items():
                new_id = mapping.get(old_id)
                if new_id:
                    new_cells[new_id] = cell
                elif old_id in new_ids and old_id not in new_cells:
                    new_cells[old_id] = cell
                else:
                    superseded.append({
                        "axis_id": old_id,
                        "cell": cell,
                        "superseded_by_migration": f"{current_version}->{definition['version']}",
                    })
                    preserved += 1
            for new_id in sorted(new_ids - set(new_cells)):
                new_cells[new_id] = {
                    "status": "not_reported",
                    "text": "Not migrated; requires explicit source review.",
                    "evidence": [],
                }
                placeholders += 1
            migrated["cells"] = new_cells
            if superseded:
                migrated["superseded_cells"] = superseded
            migrated_papers.append(migrated)
        migration_record = {
            "from_axes_version": current_version,
            "to_axes_version": definition["version"],
            "at": utc_now(),
            "mapping": dict(mapping),
            "preserved_superseded_cells": preserved,
            "new_review_placeholders": placeholders,
            "source_file": str(path),
        }
        candidate.update({
            "schema_version": 2,
            "axes": [dict(axis) for axis in definition["axes"]],
            "axes_version": definition["version"],
            "axes_source": source,
            "axes_locked": bool(candidate["papers"]),
            "axes_migrations": [*record.get("axes_migrations", []), migration_record],
            "papers": migrated_papers,
            "updated_at": utc_now(),
        })
        self._validate(candidate)
        summary = {
            "matrix_id": record["id"],
            "from_axes_version": current_version,
            "to_axes_version": definition["version"],
            "mapping": dict(mapping),
            "preserved_superseded_cells": preserved,
            "new_review_placeholders": placeholders,
            "papers": len(record["papers"]),
            "dry_run": dry_run,
            "changed": candidate != record,
            "files": [MATRIX_RELATIVE_PATH.as_posix()],
            "risk": "Axes change cell semantics; unmapped values are retained as superseded cells and new placeholders require source review.",
            "rollback": "Restore the backup snapshot created before a non-dry-run migration.",
        }
        if not dry_run:
            from .snapshot import create_snapshot
            backup = create_snapshot(self.project)
            self._write(candidate)
            summary["backup_snapshot"] = backup["snapshot"]
        return summary

    @staticmethod
    def _upsert(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        replacements = {item["id"]: item for item in incoming}
        result = [replacements.pop(item["id"], item) for item in existing]
        result.extend(replacements.values())
        return result

    def _write(self, record: dict[str, Any]) -> None:
        self._validate(record)
        atomic_text(self.path, markdown_record(record, self._render_body(record)))

    def _validate(self, record: dict[str, Any]) -> None:
        validate_record("literature_matrix", record)
        if record.get("schema_version") == 2:
            for field in ("axes_version", "axes_source", "axes_locked", "axes_migrations"):
                if field not in record:
                    raise ResearchFlowError(f"Schema-v2 literature matrix is missing {field}.")
            validate_axes_definition({
                "schema_version": 1,
                "name": record["axes_source"].get("name", "matrix"),
                "version": record["axes_version"],
                "description": "Embedded matrix axes.",
                "status": "confirmed",
                "axes": record["axes"],
            }, allow_draft=False)
            if record["papers"] and not record["axes_locked"]:
                raise ResearchFlowError("Literature matrix axes must lock when the first paper is inserted.")
        axis_ids = [axis["id"] for axis in record["axes"]]
        if len(axis_ids) != len(set(axis_ids)):
            raise ResearchFlowError("Literature matrix axis IDs must be unique.")
        paper_ids = [paper["paper_id"] for paper in record["papers"]]
        if len(paper_ids) != len(set(paper_ids)):
            raise ResearchFlowError("Literature matrix paper IDs must be unique.")
        expected_axes = set(axis_ids)

        paper_cache: dict[str, tuple[dict[str, Any], str]] = {}
        for entry in record["papers"]:
            paper_id = entry["paper_id"]
            paper = self.project.evidence.show(paper_id)
            metadata, body = paper["metadata"], paper["body"]
            document = metadata.get("source", {}).get("document") or {}
            if metadata.get("status") != "verified" or not document:
                raise ResearchFlowError(f"Matrix references unverified paper: {paper_id}")
            if entry["source_version"] != document.get("version") or entry["source_sha256"] != document.get("sha256"):
                raise ResearchFlowError(f"Matrix entry is stale for {paper_id}; its verified source fingerprint changed.")
            actual_axes = set(entry["cells"])
            missing = sorted(expected_axes - actual_axes)
            extra = sorted(actual_axes - expected_axes)
            if missing or extra:
                raise ResearchFlowError(
                    f"Incomplete matrix entry for {paper_id}: missing axes: {', '.join(missing) or 'none'}; "
                    f"unknown axes: {', '.join(extra) or 'none'}"
                )
            paper_cache[paper_id] = (metadata, body)
            for axis_id, cell in entry["cells"].items():
                if cell["status"] == "supported" and not cell["evidence"]:
                    raise ResearchFlowError(f"{paper_id}.{axis_id} is supported but has no evidence reference.")
                for ref in cell["evidence"]:
                    if "paper_id" in ref:
                        raise ResearchFlowError(f"{paper_id}.{axis_id} cell evidence must not repeat paper_id.")
                    self._validate_ref(paper_id, ref, body)

        included = set(paper_ids)
        for section in ("syntheses", "ideas"):
            seen: set[str] = set()
            for item in record[section]:
                if item["id"] in seen:
                    raise ResearchFlowError(f"Duplicate {section} ID: {item['id']}")
                seen.add(item["id"])
                for ref in item["evidence"]:
                    paper_id = ref["paper_id"]
                    if paper_id not in included:
                        raise ResearchFlowError(f"{item['id']} cites {paper_id}, which is not in this matrix.")
                    self._validate_ref(paper_id, ref, paper_cache[paper_id][1])

    @staticmethod
    def _validate_ref(paper_id: str, ref: dict[str, Any], body: str) -> None:
        for claim_id in ref["claim_ids"]:
            if not re.search(rf"\b{re.escape(claim_id)}\b", body):
                raise ResearchFlowError(f"Evidence reference {paper_id} {claim_id} is absent from the verified deep read.")

    @staticmethod
    def _citation(metadata: dict[str, Any]) -> str:
        authors = metadata.get("authors") or []
        lead = authors[0] if authors else metadata["title"]
        suffix = " et al." if len(authors) > 1 else ""
        year = metadata.get("year") or "n.d."
        return f"{lead}{suffix} {year}"

    def _render_body(self, record: dict[str, Any]) -> str:
        lines = [
            f"# {record['title']}",
            "",
            f"范围：{record['scope']}",
            "",
            "> 本文由 YAML 前置数据生成。请使用 `rf evidence matrix add|synthesize|validate|render` 修改或检查；正文不是第二份权威数据。",
            "",
            "## 证据边界",
            "",
            "- Zotero 保管书目和 PDF；矩阵只引用已通过 ResearchFlow 验证的精读记录。",
            "- 页码均以锁定 PDF 的 viewer 页码为准；论文报告结果不等于本项目复现结果。",
            "- `not_reported` 和 `not_applicable` 是明确判断，不等于遗漏比较轴。",
        ]
        for group in ("framing", "method", "evidence", "decision"):
            axes = [axis for axis in record["axes"] if axis["group"] == group]
            if not axes:
                continue
            lines.extend(["", f"## {GROUP_LABELS[group]}", ""])
            header = ["Paper", *[axis["label"] for axis in axes]]
            lines.append("| " + " | ".join(header) + " |")
            lines.append("|" + "|".join("---" for _ in header) + "|")
            for paper in record["papers"]:
                cells = [self._render_cell(paper["paper_id"], paper["cells"][axis["id"]]) for axis in axes]
                lines.append("| " + " | ".join([self._escape(paper["paper_id"]), *cells]) + " |")
        lines.extend(["", "## 纳入决定", "", "| Paper | Citation | Role | Decision | Next checks |", "|---|---|---|---|---|"])
        for paper in record["papers"]:
            next_checks = "<br>".join(self._escape(item) for item in paper["next_checks"]) or "-"
            lines.append(
                f"| {paper['paper_id']} | {self._escape(paper['citation'])} | {self._escape(paper['role'])} | "
                f"{paper['decision']} | {next_checks} |"
            )
        lines.extend(["", "## 跨论文综合", ""])
        if record["syntheses"]:
            for item in record["syntheses"]:
                refs = self._render_cross_refs(item["evidence"])
                lines.extend([
                    f"### {item['id']}", "", self._escape(item["statement"]), "",
                    f"- 强度：`{item['strength']}`", f"- 证据：{refs}", f"- 边界：{self._escape(item['caveat'])}", "",
                ])
        else:
            lines.append("尚无跨论文综合结论。")
        lines.extend(["", "## 跨论文 Idea Seeds", ""])
        if record["ideas"]:
            for item in record["ideas"]:
                lines.extend([
                    f"### {item['id']} - {self._escape(item['title'])}", "",
                    f"- 触发：{self._escape(item['trigger'])}",
                    f"- 机制：{self._escape(item['mechanism'])}",
                    f"- 最小证伪：{self._escape(item['falsification'])}",
                    f"- 风险：{self._escape(item['risks'])}",
                    f"- 新颖性：`{item['novelty']}`",
                    f"- 证据：{self._render_cross_refs(item['evidence'])}", "",
                ])
        else:
            lines.append("尚无跨论文 Idea Seed。")
        lines.extend(["", "## 可追溯来源", ""])
        for paper in record["papers"]:
            lines.append(f"- [{paper['paper_id']} 深读记录](../evidence/papers/analysis/{paper['paper_id']}.md)")
        return "\n".join(lines).rstrip() + "\n"

    def _render_cell(self, paper_id: str, cell: dict[str, Any]) -> str:
        marker = {"supported": "", "not_reported": "[未报告] ", "not_applicable": "[不适用] "}[cell["status"]]
        text = marker + self._escape(cell["text"])
        if cell["evidence"]:
            refs = "; ".join(self._render_ref(paper_id, ref) for ref in cell["evidence"])
            text += f"<br><sub>{refs}</sub>"
        return text

    def _render_cross_refs(self, refs: list[dict[str, Any]]) -> str:
        return "; ".join(self._render_ref(ref["paper_id"], ref) for ref in refs)

    @staticmethod
    def _render_ref(paper_id: str, ref: dict[str, Any]) -> str:
        parts = [paper_id, ",".join(ref["claim_ids"]), ref["pages"]]
        if ref.get("locator"):
            parts.append(str(ref["locator"]))
        return " ".join(parts)

    @staticmethod
    def _escape(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")
