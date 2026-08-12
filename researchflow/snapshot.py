from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from . import __version__
from .config import config_path, load_config, research_home
from .errors import ResearchFlowError
from .gitops import inspect_git_state
from .io import read_markdown_record, utc_now
from .project import ResearchProject


SNAPSHOT_EXTENSION = ".rfsnapshot"
_EXCLUDED_ROOTS = {"tmp", ".locks", ".restore-backups"}
_EXCLUDED_PREFIXES = {"evidence/papers/pdf"}
_SECRET_KEY = re.compile(r"(?i)(secret|token|password|api[_-]?key|credential|private[_-]?key)")


def default_snapshot_dir(project: ResearchProject) -> Path:
    return research_home() / ".snapshots" / project.data["id"]


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_member(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name or name.startswith(("/", "\\")):
        return False
    pure = PurePosixPath(name)
    if pure.is_absolute() or pure.as_posix() != name or ".." in pure.parts:
        return False
    return not any(":" in part for part in pure.parts)


def _manifest_issues(manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if manifest.get("schema_version") != 1:
        issues.append("manifest schema_version must be 1")
    for field in ("project_id", "created_at", "workspace_source"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            issues.append(f"manifest {field} must be a non-empty string")
    if not isinstance(manifest.get("external_dependencies"), dict):
        issues.append("manifest external_dependencies must be a mapping")
    excluded = manifest.get("excluded")
    if not isinstance(excluded, list) or not all(isinstance(item, str) for item in excluded):
        issues.append("manifest excluded must be a list of paths")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        issues.append("manifest files must be a list")
        return issues
    seen: set[str] = set()
    portable_seen: set[str] = set()
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            issues.append(f"manifest file entry {index} must be a mapping")
            continue
        relative = entry.get("path")
        if not isinstance(relative, str) or not _safe_member(relative):
            issues.append(f"manifest file entry {index} has an unsafe path: {relative!r}")
        elif relative in seen:
            issues.append(f"duplicate manifest file: {relative}")
        elif relative.casefold() in portable_seen:
            issues.append(f"portable path collision in manifest: {relative}")
        else:
            seen.add(relative)
            portable_seen.add(relative.casefold())
        size = entry.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            issues.append(f"manifest file entry {index} has an invalid size")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            issues.append(f"manifest file entry {index} has an invalid sha256")
    return issues


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _redact(value: Any, key: str = "") -> Any:
    if _SECRET_KEY.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(item_key): _redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _workspace_files(project: ResearchProject) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    excluded: list[str] = []
    for path in sorted(project.root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(project.root).as_posix()
        root_name = relative.split("/", 1)[0]
        if root_name in _EXCLUDED_ROOTS or any(
            relative == prefix or relative.startswith(prefix + "/") for prefix in _EXCLUDED_PREFIXES
        ):
            if path.is_file() or path.is_symlink():
                excluded.append(relative)
            continue
        if path.is_symlink():
            excluded.append(relative + " [symlink]")
            continue
        if path.is_file():
            files.append(path)
    return files, excluded


def _zotero_references(project: ResearchProject) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    folder = project.root / "evidence" / "papers" / "analysis"
    for path in sorted(folder.glob("PAPER-*.md")):
        try:
            metadata, _ = read_markdown_record(path)
        except (OSError, ResearchFlowError):
            continue
        zotero = metadata.get("source", {}).get("zotero")
        if isinstance(zotero, dict):
            refs.append({
                "paper_id": metadata.get("id"),
                "server_id": zotero.get("server_id"),
                "library": zotero.get("library"),
                "item_key": zotero.get("item_key"),
                "item_version": zotero.get("item_version"),
            })
    return refs


def _external_dependencies(project: ResearchProject) -> dict[str, Any]:
    git_state = inspect_git_state(project.repo).as_dict()
    config = load_config()
    zotero_config = config.get("preferences", {}).get("literature", {}).get("zotero", {})
    return {
        "independent_repo": {"path": str(project.repo), "git": git_state, "backed_up": False},
        "zotero": {
            "configured": _redact(zotero_config),
            "linked_sources": _zotero_references(project),
            "pdfs_backed_up": False,
        },
        "project_paths": _redact(project.data.get("paths", {})),
        "large_assets_backed_up": False,
        "global_config": {"path": str(config_path()), "included": False},
    }


def create_snapshot(
    project: ResearchProject,
    output_dir: Path | None = None,
    *,
    include_redacted_config: bool = False,
) -> dict[str, Any]:
    destination = (output_dir or default_snapshot_dir(project)).expanduser().resolve()
    if _inside(destination, project.root):
        raise ResearchFlowError("Snapshot output must be outside the project workspace to avoid recursive or partial backups.")
    destination.mkdir(parents=True, exist_ok=True)
    files, excluded = _workspace_files(project)
    entries = []
    for path in files:
        relative = path.relative_to(project.root).as_posix()
        entries.append({"path": relative, "size": path.stat().st_size, "sha256": _sha256_file(path)})
    external = _external_dependencies(project)
    redacted_config: bytes | None = None
    if include_redacted_config:
        redacted_config = yaml.safe_dump(_redact(load_config()), sort_keys=False, allow_unicode=True).encode("utf-8")
        external["global_config"]["included"] = True
        external["global_config"]["mode"] = "redacted"
        external["global_config"]["size"] = len(redacted_config)
        external["global_config"]["sha256"] = _sha256_bytes(redacted_config)
    created = utc_now()
    manifest = {
        "schema_version": 1,
        "snapshot_format": "researchflow-project-snapshot-v1",
        "project_id": project.data["id"],
        "researchflow_version": __version__,
        "created_at": created,
        "workspace_source": str(project.root),
        "files": entries,
        "excluded": sorted(excluded),
        "external_dependencies": external,
    }
    manifest_bytes = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode("utf-8")
    manifest_hash = _sha256_bytes(manifest_bytes)
    stamp = created.replace("-", "").replace(":", "").replace("+00:00", "Z")
    target = destination / f"{project.data['id']}-{stamp}-{manifest_hash[:8]}{SNAPSHOT_EXTENSION}"
    if target.exists():
        raise ResearchFlowError(f"Snapshot already exists: {target}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".partial", dir=destination)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr("manifest.yaml", manifest_bytes)
            archive.writestr("manifest.sha256", manifest_hash + "\n")
            if include_redacted_config:
                archive.writestr("global-config.redacted.yaml", redacted_config)
            for path, entry in zip(files, entries):
                archive.write(path, f"workspace/{entry['path']}")
        with temporary.open("r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        verification = verify_snapshot(temporary, expected_project_id=project.data["id"])
        if not verification["valid"]:
            raise ResearchFlowError(
                "Snapshot creation produced an invalid archive: " + "; ".join(verification["issues"])
            )
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "snapshot": str(target),
        "project_id": project.data["id"],
        "files": len(entries),
        "bytes": sum(item["size"] for item in entries),
        "manifest_sha256": manifest_hash,
        "excluded": len(excluded),
        "external_assets_backed_up": False,
    }


def list_snapshots(project: ResearchProject, input_dir: Path | None = None) -> list[dict[str, Any]]:
    source = (input_dir or default_snapshot_dir(project)).expanduser().resolve()
    if not source.exists():
        return []
    result = []
    for path in sorted(source.glob(f"*{SNAPSHOT_EXTENSION}")):
        try:
            manifest = show_snapshot(path)
            if manifest.get("project_id") != project.data["id"]:
                continue
            verification = verify_snapshot(path, expected_project_id=project.data["id"])
            result.append({
                "path": str(path),
                "project_id": manifest.get("project_id"),
                "created_at": manifest.get("created_at"),
                "files": len(manifest.get("files", [])),
                "valid": verification["valid"],
                "issues": verification["issues"],
            })
        except ResearchFlowError as exc:
            if path.name.startswith(f"{project.data['id']}-"):
                result.append({"path": str(path), "error": str(exc)})
    return result


def _read_archive(snapshot: Path) -> tuple[zipfile.ZipFile, dict[str, Any], bytes, list[str]]:
    path = snapshot.expanduser().resolve()
    if not path.is_file():
        raise ResearchFlowError(f"Snapshot does not exist: {path}")
    try:
        archive = zipfile.ZipFile(path, "r")
        names = archive.namelist()
        if len(names) != len(set(names)):
            archive.close()
            raise ResearchFlowError("Snapshot contains duplicate archive paths.")
        unsafe = [name for name in names if not _safe_member(name)]
        if unsafe:
            archive.close()
            raise ResearchFlowError(f"Snapshot contains unsafe path(s): {', '.join(unsafe)}")
        manifest_bytes = archive.read("manifest.yaml")
        stored_hash = archive.read("manifest.sha256").decode("ascii").strip()
    except (KeyError, OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        try:
            archive.close()
        except UnboundLocalError:
            pass
        raise ResearchFlowError(f"Invalid ResearchFlow snapshot {path}: {exc}") from exc
    if stored_hash != _sha256_bytes(manifest_bytes):
        archive.close()
        raise ResearchFlowError("Snapshot manifest hash mismatch; the manifest was changed or corrupted.")
    try:
        manifest = yaml.safe_load(manifest_bytes.decode("utf-8")) or {}
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        archive.close()
        raise ResearchFlowError(f"Snapshot manifest is invalid YAML: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("snapshot_format") != "researchflow-project-snapshot-v1":
        archive.close()
        raise ResearchFlowError("Unsupported snapshot manifest format.")
    manifest_issues = _manifest_issues(manifest)
    if manifest_issues:
        archive.close()
        raise ResearchFlowError("Invalid snapshot manifest: " + "; ".join(manifest_issues))
    return archive, manifest, manifest_bytes, names


def show_snapshot(snapshot: Path) -> dict[str, Any]:
    archive, manifest, _, _ = _read_archive(snapshot)
    archive.close()
    return manifest


def verify_snapshot(snapshot: Path, *, expected_project_id: str | None = None) -> dict[str, Any]:
    path = snapshot.expanduser().resolve()
    try:
        archive, manifest, _, names = _read_archive(path)
    except ResearchFlowError as exc:
        return {"snapshot": str(path), "valid": False, "issues": [str(exc)]}
    issues: list[str] = []
    if expected_project_id is not None and manifest.get("project_id") != expected_project_id:
        issues.append(
            f"snapshot belongs to {manifest.get('project_id')}, not selected project {expected_project_id}"
        )
    expected = {"manifest.yaml", "manifest.sha256"}
    if manifest.get("external_dependencies", {}).get("global_config", {}).get("included"):
        expected.add("global-config.redacted.yaml")
        config_entry = manifest["external_dependencies"]["global_config"]
        if "global-config.redacted.yaml" not in names:
            issues.append("missing file: global-config.redacted.yaml")
        else:
            config_payload = archive.read("global-config.redacted.yaml")
            if len(config_payload) != config_entry.get("size"):
                issues.append("size mismatch: global-config.redacted.yaml")
            if _sha256_bytes(config_payload) != config_entry.get("sha256"):
                issues.append("hash mismatch: global-config.redacted.yaml")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        entries = []
        issues.append("manifest files must be a list")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            issues.append("manifest contains an invalid file entry")
            continue
        relative = entry["path"]
        member = f"workspace/{relative}"
        if not _safe_member(member):
            issues.append(f"unsafe manifest path: {relative}")
            continue
        if member in seen:
            issues.append(f"duplicate manifest file: {relative}")
            continue
        seen.add(member)
        expected.add(member)
        if member not in names:
            issues.append(f"missing file: {relative}")
            continue
        try:
            payload = archive.read(member)
        except (KeyError, RuntimeError, zipfile.BadZipFile) as exc:
            issues.append(f"unreadable file: {relative}: {exc}")
            continue
        if len(payload) != entry.get("size"):
            issues.append(f"size mismatch: {relative}")
        if _sha256_bytes(payload) != entry.get("sha256"):
            issues.append(f"hash mismatch: {relative}")
    extras = sorted(set(names) - expected)
    if extras:
        issues.extend(f"extra file: {name}" for name in extras)
    archive.close()
    return {
        "snapshot": str(path),
        "project_id": manifest.get("project_id"),
        "valid": not issues,
        "files": len(entries),
        "issues": issues,
        "scope": "ResearchFlow project workspace records only; external repo, Zotero PDFs, datasets, weights, and large assets are references only.",
    }


def restore_snapshot(
    project: ResearchProject,
    snapshot: Path,
    *,
    target: Path | None = None,
    in_place: bool = False,
    yes: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    snapshot = snapshot.expanduser().resolve()
    verification = verify_snapshot(snapshot, expected_project_id=project.data["id"])
    if not verification["valid"]:
        raise ResearchFlowError("Snapshot verification failed: " + "; ".join(verification["issues"]))
    manifest = show_snapshot(snapshot)
    if manifest.get("project_id") != project.data["id"]:
        raise ResearchFlowError(
            f"Snapshot belongs to {manifest.get('project_id')}, not selected project {project.data['id']}."
        )
    if in_place and target is not None:
        raise ResearchFlowError("Use either --in-place or --target, not both.")
    if in_place and not yes:
        raise ResearchFlowError("In-place restore requires explicit --in-place --yes confirmation.")
    if in_place:
        destination = project.root
    else:
        stamp = str(manifest["created_at"]).replace("-", "").replace(":", "").replace("+00:00", "Z")
        destination = (target or (snapshot.parent / "restored" / f"{project.data['id']}-{stamp}")).expanduser().resolve()
        if _inside(destination, project.root):
            raise ResearchFlowError(
                f"Restore target must be outside the live project workspace: {destination}"
            )
        if destination.exists():
            raise ResearchFlowError(f"Restore target already exists; refusing to overwrite: {destination}")
    plan = {
        "snapshot": str(snapshot),
        "project_id": project.data["id"],
        "target": str(destination),
        "in_place": in_place,
        "files": len(manifest["files"]),
        "dry_run": dry_run,
        "backup": None,
    }
    if dry_run:
        return plan
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.restore.", dir=destination.parent))
    backup: Path | None = None
    try:
        archive, live_manifest, _, _ = _read_archive(snapshot)
        try:
            if live_manifest != manifest:
                raise ResearchFlowError("Snapshot changed between verification and restore; retry with a stable archive.")
            for entry in manifest["files"]:
                relative = PurePosixPath(entry["path"])
                output = temporary.joinpath(*relative.parts)
                if not _inside(output, temporary):
                    raise ResearchFlowError(f"Restore path escapes target: {entry['path']}")
                output.parent.mkdir(parents=True, exist_ok=True)
                payload = archive.read(f"workspace/{entry['path']}")
                if len(payload) != entry["size"] or _sha256_bytes(payload) != entry["sha256"].casefold():
                    raise ResearchFlowError(f"Snapshot payload changed during restore: {entry['path']}")
                with output.open("wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
        finally:
            archive.close()
        if in_place:
            backup_root = project.root.parent / ".restore-backups"
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root / f"{project.data['id']}-{utc_now().replace(':', '').replace('+00:00', 'Z')}"
            os.replace(project.root, backup)
            try:
                os.replace(temporary, project.root)
            except Exception:
                os.replace(backup, project.root)
                raise
            destination = project.root
        else:
            os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    plan["target"] = str(destination)
    plan["backup"] = str(backup) if backup else None
    plan["restored"] = True
    return plan
