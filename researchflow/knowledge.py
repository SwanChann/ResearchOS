from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .artifact import ArtifactStore
from .errors import ResearchFlowError
from .io import atomic_text, read_jsonl, read_markdown_record, read_yaml
from .literature import LiteratureMatrixStore


BEGIN = "<!-- RESEARCHFLOW:GENERATED:BEGIN -->"
END = "<!-- RESEARCHFLOW:GENERATED:END -->"


class KnowledgeStore:
    """Build the machine-owned navigation block while preserving manual prose."""

    def __init__(self, project):
        self.project = project
        self.path = project.root / "KNOWLEDGE.md"

    @staticmethod
    def _generated_match(text: str):
        begin_count, end_count = text.count(BEGIN), text.count(END)
        if begin_count != end_count or begin_count > 1:
            raise ResearchFlowError(
                f"KNOWLEDGE.md has ambiguous generated-region markers: {begin_count} BEGIN and {end_count} END."
            )
        if not begin_count:
            return None
        match = re.search(rf"{re.escape(BEGIN)}.*?{re.escape(END)}", text, flags=re.DOTALL)
        if not match:
            raise ResearchFlowError("KNOWLEDGE.md generated-region markers are out of order.")
        return match

    def inventory(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for path in sorted((self.project.root / "evidence" / "papers" / "analysis").glob("PAPER-*.md")):
            try:
                metadata, _ = read_markdown_record(path)
                status = metadata.get("status", "draft")
                labels = [status]
                from .review import paper_verification
                verification = paper_verification(metadata)
                if status == "verified" and verification["semantic_review_pending"]:
                    labels.append("human-review-pending")
                if verification["stale_reviews"]:
                    labels.append("stale")
                entries.append(self._entry(metadata["id"], metadata.get("title", path.stem), "Paper", path, labels))
            except (ResearchFlowError, OSError) as exc:
                entries.append(self._entry(path.stem, path.stem, "Paper", path, ["broken"], str(exc)))
        for folder, kind in (("observations", "Observation"), ("hypotheses", "Hypothesis"), ("decisions", "Decision")):
            for path in sorted((self.project.root / "memory" / folder).glob("*.md")):
                try:
                    metadata, _ = read_markdown_record(path)
                    status = metadata.get("status") or ("active" if kind != "Decision" else "active")
                    entries.append(self._entry(metadata.get("id", path.stem), metadata.get("title") or metadata.get("decision") or path.stem, kind, path, [str(status)]))
                except (ResearchFlowError, OSError) as exc:
                    entries.append(self._entry(path.stem, path.stem, kind, path, ["broken"], str(exc)))
        for path in sorted((self.project.root / "experiments" / "cards").glob("EXP-*.yaml")):
            try:
                data = read_yaml(path)
                entries.append(self._entry(data["id"], data.get("title", path.stem), "Experiment", path, [str(data.get("status", "draft")).lower()]))
            except (ResearchFlowError, OSError) as exc:
                entries.append(self._entry(path.stem, path.stem, "Experiment", path, ["broken"], str(exc)))
        for path in sorted((self.project.root / "runs").glob("RUN-*/run.yaml")):
            try:
                data = read_yaml(path)
                labels = [str(data.get("status", "draft"))]
                if data.get("test_only"):
                    labels.append("test-only")
                entries.append(self._entry(data["id"], f"{data['id']} / {data.get('experiment', 'unknown')}", "Run", path, labels))
            except (ResearchFlowError, OSError) as exc:
                entries.append(self._entry(path.parent.name, path.parent.name, "Run", path, ["broken"], str(exc)))
        matrix_path = self.project.root / ".research" / "literature_matrix.md"
        if matrix_path.exists():
            try:
                matrix = LiteratureMatrixStore(self.project)
                record = matrix.load()
                labels = [record["status"]]
                from .review import matrix_review_status
                review = matrix_review_status(record)
                if review["semantic_review_pending"]:
                    labels.append("human-review-pending")
                if review["stale_reviews"]:
                    labels.append("stale")
                entries.append(self._entry(record["id"], record["title"], "Matrix", matrix_path, labels))
            except ResearchFlowError as exc:
                entries.append(self._entry("LITMATRIX-0001", "Literature matrix", "Matrix", matrix_path, ["broken", "stale"], str(exc)))
        artifacts = ArtifactStore(self.project)
        registry = artifacts.load()
        verified = {item["id"]: item for item in artifacts.verify()["results"]}
        for item in registry["artifacts"]:
            labels = [item["status"]]
            if not verified[item["id"]]["valid"]:
                labels.append("broken")
            entries.append(self._entry(item["id"], item["title"], "Artifact", self.project.root / item["path"], labels))
        return entries

    def summary(self) -> dict[str, Any]:
        entries = self.inventory()
        counts: dict[str, int] = {}
        for item in entries:
            for label in item["labels"]:
                counts[label] = counts.get(label, 0) + 1
        return {"records": len(entries), "by_state": counts, "broken_or_stale": [item["id"] for item in entries if {"broken", "stale"} & set(item["labels"])]}

    def generated_block(self) -> str:
        entries = self.inventory()
        lines = [BEGIN, "", "## ResearchFlow Generated Index", "", "> Machine-generated navigation. File integrity, contract checks, and review state do not establish scientific claims."]
        order = ("Paper", "Observation", "Hypothesis", "Experiment", "Run", "Decision", "Matrix", "Artifact")
        for kind in order:
            selected = [item for item in entries if item["kind"] == kind]
            lines.extend(["", f"### {kind}s", ""])
            if not selected:
                lines.append("- None registered.")
                continue
            for item in selected:
                relative = item["path"]
                label = ", ".join(item["labels"])
                suffix = f"; {item['issue']}" if item.get("issue") else ""
                lines.append(f"- [{item['id']}]({relative}) — {item['title']} [{label}]{suffix}")
        lines.extend(["", END])
        return "\n".join(lines)

    def rebuild(self, *, dry_run: bool = False) -> dict[str, Any]:
        current = self.path.read_text(encoding="utf-8") if self.path.exists() else "# Knowledge Index\n"
        generated = self.generated_block()
        match = self._generated_match(current)
        if match:
            updated = current[:match.start()] + generated + current[match.end():]
        else:
            updated = current.rstrip() + "\n\n" + generated + "\n"
        updated = updated.rstrip() + "\n"
        changed = updated != current
        if changed and not dry_run:
            atomic_text(self.path, updated)
        return {
            "path": str(self.path), "changed": changed, "dry_run": dry_run,
            "records": len(self.inventory()), "manual_content_preserved": True,
        }

    def check(self) -> dict[str, Any]:
        current = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        match = self._generated_match(current)
        expected = self.generated_block()
        actual = match.group(0) if match else None
        stale = actual != expected
        expected_ids = {item["id"] for item in self.inventory()}
        listed_ids = set(re.findall(r"\[(?:((?:PAPER|OBS|HYP|EXP|RUN|DEC|LITMATRIX|ARTIFACT)-\d+))\]", actual or ""))
        broken_links = []
        if actual:
            for relative in re.findall(r"\]\(([^)]+)\)", actual):
                if not (self.project.root / relative).is_file():
                    broken_links.append(relative)
        superseded_current = []
        for item in ArtifactStore(self.project).list("superseded"):
            if actual and f"[{item['id']}]" in actual and "[superseded" not in next((line for line in actual.splitlines() if f"[{item['id']}]" in line), ""):
                superseded_current.append(item["id"])
        return {
            "valid": bool(actual) and not stale and not broken_links and not superseded_current,
            "generated_region_present": bool(actual),
            "stale": stale,
            "missing_registered_ids": sorted(expected_ids - listed_ids),
            "unknown_listed_ids": sorted(listed_ids - expected_ids),
            "broken_links": sorted(set(broken_links)),
            "superseded_listed_as_current": superseded_current,
        }

    def _entry(self, identifier: str, title: str, kind: str, path: Path, labels: list[str], issue: str | None = None) -> dict[str, Any]:
        return {
            "id": identifier,
            "title": str(title).replace("\n", " "),
            "kind": kind,
            "path": path.resolve().relative_to(self.project.root.resolve()).as_posix(),
            "labels": labels,
            "issue": issue,
        }
