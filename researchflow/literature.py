from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .errors import ResearchFlowError
from .io import atomic_text, markdown_record, read_markdown_record, read_yaml, utc_now
from .project import ResearchProject
from .schema import validate_record


MATRIX_RELATIVE_PATH = Path(".research/literature_matrix.md")

DEFAULT_AXES = (
    {"id": "research_question", "label": "研究问题", "group": "framing"},
    {"id": "architecture", "label": "核心架构", "group": "method"},
    {"id": "planning_control_interface", "label": "规划-控制接口", "group": "method"},
    {"id": "temporal_structure", "label": "时序结构", "group": "method"},
    {"id": "training_data", "label": "训练与数据", "group": "method"},
    {"id": "benchmarks", "label": "基准与协议", "group": "evidence"},
    {"id": "main_results", "label": "主要结果", "group": "evidence"},
    {"id": "real_world", "label": "实机证据", "group": "evidence"},
    {"id": "deployment_dependencies", "label": "部署依赖", "group": "evidence"},
    {"id": "failure_boundary", "label": "失败边界", "group": "evidence"},
    {"id": "relevance", "label": "相关性", "group": "decision"},
    {"id": "use_as", "label": "文献角色", "group": "decision"},
)

GROUP_LABELS = {
    "framing": "问题框定",
    "method": "方法与系统",
    "evidence": "证据与边界",
    "decision": "综述决策",
}


class LiteratureMatrixStore:
    """A structured, page-cited cross-paper matrix with a generated Markdown view."""

    def __init__(self, project: ResearchProject):
        self.project = project
        self.path = project.root / MATRIX_RELATIVE_PATH

    def initialize(self, title: str, scope: str) -> Path:
        if self.path.exists():
            raise ResearchFlowError(f"Literature matrix already exists: {self.path}")
        record = {
            "schema_version": 1,
            "id": "LITMATRIX-0001",
            "title": title.strip(),
            "scope": scope.strip(),
            "status": "active",
            "citation_basis": "pdf_page",
            "axes": [dict(axis) for axis in DEFAULT_AXES],
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
        statuses = {"supported": 0, "not_reported": 0, "not_applicable": 0}
        for paper in record["papers"]:
            for cell in paper["cells"].values():
                statuses[cell["status"]] += 1
        return {
            "path": str(self.path),
            "matrix_id": record["id"],
            "papers": len(record["papers"]),
            "axes": len(record["axes"]),
            "syntheses": len(record["syntheses"]),
            "ideas": len(record["ideas"]),
            "cell_status": statuses,
            "valid": True,
        }

    def add_entry_file(self, entry_path: Path) -> str:
        entry = read_yaml(entry_path.expanduser().resolve())
        return self.add_entry(entry)

    def add_entry(self, entry: dict[str, Any]) -> str:
        record = self.load()
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
        record["papers"].append(normalized)
        record["updated_at"] = utc_now()
        self._write(record)
        return paper_id

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

    def _write(self, record: dict[str, Any]) -> None:
        self._validate(record)
        atomic_text(self.path, markdown_record(record, self._render_body(record)))

    def _validate(self, record: dict[str, Any]) -> None:
        validate_record("literature_matrix", record)
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
            "> 本文由 YAML 前置数据生成。请使用 `rf evidence matrix add|validate|render` 修改或检查；正文不是第二份权威数据。",
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
