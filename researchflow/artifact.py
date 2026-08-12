from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

from .config import research_home
from .errors import ResearchFlowError
from .ids import allocate_id
from .io import read_yaml, utc_now, write_yaml
from .records import record_exists
from .schema import validate_record


REGISTRY_RELATIVE_PATH = Path(".research/artifacts.yaml")
SCANNABLE_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".jsonl", ".csv", ".tsv"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ArtifactStore:
    """Atomic registry for project-scoped research products.

    Hash verification establishes file integrity only. It does not establish
    semantic correctness, reproduction, novelty, or a scientific claim.
    """

    def __init__(self, project):
        self.project = project
        self.path = project.root / REGISTRY_RELATIVE_PATH

    def _empty(self) -> dict[str, Any]:
        return {"schema_version": 1, "artifacts": [], "updated_at": utc_now()}

    def load(self) -> dict[str, Any]:
        registry = read_yaml(self.path) if self.path.exists() else self._empty()
        validate_record("artifact_registry", registry)
        self._validate_registry(registry)
        return registry

    def initialize(self) -> Path:
        if not self.path.exists():
            self._write(self._empty())
        return self.path

    def _write(self, registry: dict[str, Any]) -> None:
        candidate = dict(registry)
        candidate["updated_at"] = utc_now()
        validate_record("artifact_registry", candidate)
        self._validate_registry(candidate)
        write_yaml(self.path, candidate)

    def _registry_file(self, value: str) -> Path:
        if not value or "\\" in value or "\x00" in value:
            raise ResearchFlowError(f"Artifact registry contains an unsafe project-relative path: {value!r}")
        pure = PurePosixPath(value)
        if pure.is_absolute() or pure.as_posix() != value or ".." in pure.parts or any(":" in part for part in pure.parts):
            raise ResearchFlowError(f"Artifact registry contains an unsafe project-relative path: {value!r}")
        root = self.project.root.resolve()
        resolved = root.joinpath(*pure.parts).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ResearchFlowError(f"Artifact registry path escapes the project workspace: {value}") from exc
        if resolved == self.path.resolve():
            raise ResearchFlowError("The artifact registry cannot register itself.")
        return resolved

    def _validate_registry(self, registry: dict[str, Any]) -> None:
        items = registry["artifacts"]
        identifiers = [item["id"] for item in items]
        paths = [item["path"] for item in items]
        if len(identifiers) != len(set(identifiers)):
            raise ResearchFlowError("Artifact registry contains duplicate IDs.")
        if len(paths) != len({path.casefold() for path in paths}):
            raise ResearchFlowError("Artifact registry contains duplicate paths.")
        for path in paths:
            self._registry_file(path)
        by_id = {item["id"]: item for item in items}
        for item in items:
            replacement = item["superseded_by"]
            if item["status"] == "superseded" and not replacement:
                raise ResearchFlowError(f"Artifact {item['id']} is superseded but has no superseded_by link.")
            if replacement:
                if item["status"] != "superseded":
                    raise ResearchFlowError(f"Artifact {item['id']} has superseded_by but is not marked superseded.")
                if replacement not in by_id or item["id"] not in by_id[replacement]["supersedes"]:
                    raise ResearchFlowError(f"Artifact lineage is not reciprocal: {item['id']} -> {replacement}.")
            for old_id in item["supersedes"]:
                if old_id not in by_id or by_id[old_id]["superseded_by"] != item["id"]:
                    raise ResearchFlowError(f"Artifact lineage is not reciprocal: {item['id']} supersedes {old_id}.")
        for item in items:
            seen: set[str] = set()
            current = item
            while current["superseded_by"]:
                if current["id"] in seen:
                    raise ResearchFlowError(f"Artifact supersession cycle detected at {current['id']}.")
                seen.add(current["id"])
                current = by_id[current["superseded_by"]]

    def _relative_file(self, value: Path) -> tuple[Path, str]:
        root = self.project.root.resolve()
        candidate = value.expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise ResearchFlowError(f"Artifact path escapes the project workspace: {resolved}") from exc
        if not resolved.is_file():
            raise ResearchFlowError(f"Artifact file does not exist: {resolved}")
        if relative == REGISTRY_RELATIVE_PATH.as_posix():
            raise ResearchFlowError("The artifact registry cannot register itself.")
        return resolved, relative

    def _require_refs(self, refs: list[str], registry: dict[str, Any]) -> None:
        artifact_ids = {item["id"] for item in registry["artifacts"]}
        for ref in refs:
            if ref in artifact_ids:
                continue
            if not record_exists(self.project, ref):
                raise ResearchFlowError(f"Broken artifact reference {ref}: no matching record in this project.")

    def add(
        self,
        path: Path,
        *,
        title: str,
        artifact_type: str,
        status: str = "draft",
        authority: str = "researchflow_workspace",
        derived_from: list[str] | None = None,
        evidence: list[str] | None = None,
        schema: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        source, relative = self._relative_file(path)
        derived_from, evidence = derived_from or [], evidence or []
        registry = self.load()
        self._require_refs([*derived_from, *evidence], registry)
        existing = next((item for item in registry["artifacts"] if item["path"] == relative), None)
        comparable = {
            "title": title.strip(), "type": artifact_type.strip(), "status": status,
            "authority": authority.strip(), "derived_from": derived_from, "evidence": evidence,
            "schema": schema, "version": version,
        }
        if existing:
            if all(existing.get(key) == value for key, value in comparable.items()):
                return {"artifact": existing, "created": False, "idempotent": True}
            raise ResearchFlowError(f"Artifact path is already registered with different metadata: {relative} ({existing['id']})")
        now = utc_now()
        item = {
            "id": allocate_id(research_home(), "ARTIFACT"),
            **comparable,
            "path": relative,
            "sha256": _sha256(source),
            "supersedes": [],
            "superseded_by": None,
            "created_at": now,
            "updated_at": now,
        }
        candidate = {**registry, "artifacts": [*registry["artifacts"], item]}
        self._write(candidate)
        return {"artifact": item, "created": True, "idempotent": False}

    def preflight_request(self, request_path: Path) -> dict[str, Any]:
        request = read_yaml(request_path.expanduser().resolve())
        required = {"path", "title", "type", "status", "authority", "derived_from", "evidence"}
        missing = sorted(required - set(request))
        if missing:
            raise ResearchFlowError(f"Artifact request is missing: {', '.join(missing)}")
        if request["status"] not in {"draft", "active", "verified"}:
            raise ResearchFlowError("Artifact request has invalid status.")
        source, relative = self._relative_file(Path(str(request["path"])))
        if not isinstance(request["derived_from"], list) or not isinstance(request["evidence"], list):
            raise ResearchFlowError("Artifact derived_from and evidence must be lists.")
        registry = self.load()
        self._require_refs([*request["derived_from"], *request["evidence"]], registry)
        return {
            "valid": True, "path": relative, "sha256": _sha256(source),
            "would_register": not any(item["path"] == relative for item in registry["artifacts"]),
            "meaning": "File contract and references only; scientific claims are not established.",
        }

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        items = self.load()["artifacts"]
        return [item for item in items if not status or item["status"] == status]

    def show(self, artifact_id: str) -> dict[str, Any]:
        item = next((item for item in self.list() if item["id"] == artifact_id), None)
        if not item:
            raise ResearchFlowError(f"Artifact not found: {artifact_id}")
        return item

    def verify(self, artifact_id: str | None = None) -> dict[str, Any]:
        registry = self.load()
        items = [self.show(artifact_id)] if artifact_id else registry["artifacts"]
        known = {item["id"] for item in registry["artifacts"]}
        results = []
        for item in items:
            path = self._registry_file(item["path"])
            actual_hash = _sha256(path) if path.is_file() else None
            broken = [
                ref for ref in [*item["derived_from"], *item["evidence"], *item["supersedes"]]
                if ref not in known and not record_exists(self.project, ref)
            ]
            if item["superseded_by"] and item["superseded_by"] not in known:
                broken.append(item["superseded_by"])
            results.append({
                "id": item["id"], "path": item["path"], "exists": path.is_file(),
                "hash_matches": actual_hash == item["sha256"], "actual_sha256": actual_hash,
                "broken_references": broken,
                "valid": path.is_file() and actual_hash == item["sha256"] and not broken,
            })
        return {
            "valid": all(item["valid"] for item in results),
            "results": results,
            "meaning": "File integrity and registry references only; scientific claims are not established.",
        }

    def refresh(self, artifact_id: str) -> dict[str, Any]:
        registry = self.load()
        item = next((item for item in registry["artifacts"] if item["id"] == artifact_id), None)
        if not item:
            raise ResearchFlowError(f"Artifact not found: {artifact_id}")
        path = self._registry_file(item["path"])
        if not path.is_file():
            raise ResearchFlowError(f"Artifact file does not exist: {path}")
        item = {**item, "sha256": _sha256(path), "updated_at": utc_now()}
        candidate = {**registry, "artifacts": [item if value["id"] == artifact_id else value for value in registry["artifacts"]]}
        self._write(candidate)
        return item

    def supersede(self, old_id: str, new_id: str) -> dict[str, Any]:
        if old_id == new_id:
            raise ResearchFlowError("An artifact cannot supersede itself.")
        registry = self.load()
        by_id = {item["id"]: item for item in registry["artifacts"]}
        if old_id not in by_id or new_id not in by_id:
            raise ResearchFlowError("Both old and replacement artifact IDs must exist.")
        old, new = by_id[old_id], by_id[new_id]
        if old["superseded_by"] == new_id and old_id in new["supersedes"]:
            return {"old": old_id, "new": new_id, "changed": False}
        if old["superseded_by"] and old["superseded_by"] != new_id:
            raise ResearchFlowError(f"{old_id} is already superseded by {old['superseded_by']}.")
        now = utc_now()
        by_id[old_id] = {**old, "status": "superseded", "superseded_by": new_id, "updated_at": now}
        by_id[new_id] = {**new, "supersedes": list(dict.fromkeys([*new["supersedes"], old_id])), "updated_at": now}
        self._write({**registry, "artifacts": [by_id[item["id"]] for item in registry["artifacts"]]})
        return {"old": old_id, "new": new_id, "changed": True}

    def migrate(self, scan: Path, *, dry_run: bool = False) -> dict[str, Any]:
        root = self.project.root.resolve()
        scan_path = scan.expanduser()
        if not scan_path.is_absolute():
            scan_path = root / scan_path
        scan_path = scan_path.resolve()
        try:
            scan_path.relative_to(root)
        except ValueError as exc:
            raise ResearchFlowError(f"Artifact migration scan path escapes the project workspace: {scan_path}") from exc
        if not scan_path.is_dir():
            raise ResearchFlowError(f"Artifact migration scan directory does not exist: {scan_path}")
        registry = self.load()
        registered = {item["path"] for item in registry["artifacts"]}
        candidates = []
        for path in sorted(scan_path.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SCANNABLE_SUFFIXES:
                continue
            resolved = path.resolve()
            try:
                relative = resolved.relative_to(root).as_posix()
            except ValueError:
                continue
            if relative not in registered and resolved != self.path.resolve():
                candidates.append(path)
        result = {
            "scan": str(scan_path),
            "files": [path.resolve().relative_to(root).as_posix() for path in candidates],
            "count": len(candidates),
            "dry_run": dry_run,
            "changed": bool(candidates) and not dry_run,
            "risk": "Imported records are draft artifacts; registration does not make their contents semantically correct.",
            "rollback": "Restore the backup snapshot created before a non-dry-run migration.",
        }
        if dry_run or not candidates:
            return result
        from .snapshot import create_snapshot
        backup = create_snapshot(self.project)
        for path in candidates:
            self.add(path, title=path.stem, artifact_type="migration-import", status="draft")
        result["backup_snapshot"] = backup["snapshot"]
        return result
