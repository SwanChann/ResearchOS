from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest
import yaml

from researchflow.errors import ResearchFlowError
from researchflow.io import read_yaml, write_yaml
from researchflow.project import ResearchProject, add_project
from researchflow.snapshot import create_snapshot, list_snapshots, restore_snapshot, show_snapshot, verify_snapshot


def _project(rf_env) -> ResearchProject:
    add_project("toy", rf_env["repo"])
    return ResearchProject.open("toy")


def _rewrite(snapshot: Path, transform) -> None:
    with zipfile.ZipFile(snapshot, "r") as source:
        entries = [(item, source.read(item.filename)) for item in source.infolist()]
    with zipfile.ZipFile(snapshot, "w", compression=zipfile.ZIP_DEFLATED) as target:
        transform(target, entries)


def _rewrite_manifest(snapshot: Path, transform) -> None:
    def rewrite(target, entries):
        payloads = {item.filename: payload for item, payload in entries}
        manifest = yaml.safe_load(payloads["manifest.yaml"])
        transform(manifest)
        manifest_bytes = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode("utf-8")
        payloads["manifest.yaml"] = manifest_bytes
        payloads["manifest.sha256"] = (hashlib.sha256(manifest_bytes).hexdigest() + "\n").encode("ascii")
        for item, _ in entries:
            target.writestr(item, payloads[item.filename])
    _rewrite(snapshot, rewrite)


def test_snapshot_create_list_show_verify_and_scope(rf_env, tmp_path):
    project = _project(rf_env)
    config = read_yaml(rf_env["config"])
    config["future_api_token"] = "DO-NOT-EXPORT"
    write_yaml(rf_env["config"], config)
    chinese = project.root / ".research" / "中文记录.md"
    chinese.write_text("可恢复的普通文件。\n", encoding="utf-8")
    (project.root / "tmp" / "large.bin").parent.mkdir(parents=True, exist_ok=True)
    (project.root / "tmp" / "large.bin").write_bytes(b"x" * 1024)
    legacy_pdf = project.root / "evidence" / "papers" / "pdf" / "PAPER-9999.pdf"
    legacy_pdf.write_bytes(b"%PDF TEST")
    (rf_env["repo"] / "external.bin").write_bytes(b"external repo content")

    result = create_snapshot(project, tmp_path / "backups", include_redacted_config=True)
    snapshot = Path(result["snapshot"])
    assert snapshot.suffix == ".rfsnapshot"
    assert list_snapshots(project, snapshot.parent)[0]["project_id"] == "toy"
    manifest = show_snapshot(snapshot)
    paths = {item["path"] for item in manifest["files"]}
    assert ".research/中文记录.md" in paths
    assert "tmp/large.bin" not in paths
    assert "evidence/papers/pdf/PAPER-9999.pdf" not in paths
    assert "external.bin" not in paths
    assert manifest["external_dependencies"]["independent_repo"]["backed_up"] is False
    assert manifest["external_dependencies"]["zotero"]["pdfs_backed_up"] is False
    with zipfile.ZipFile(snapshot) as archive:
        assert "global-config.redacted.yaml" in archive.namelist()
        redacted = archive.read("global-config.redacted.yaml")
        assert b"DO-NOT-EXPORT" not in redacted
        assert b"<redacted>" in redacted
    assert len(manifest["external_dependencies"]["global_config"]["sha256"]) == 64
    assert verify_snapshot(snapshot)["valid"] is True


def test_snapshot_verify_detects_corruption_missing_extra_and_manifest_tamper(rf_env, tmp_path):
    project = _project(rf_env)
    (project.root / ".research" / "record.md").write_text("TEST record\n", encoding="utf-8")

    corrupted = Path(create_snapshot(project, tmp_path / "corrupt")["snapshot"])
    def corrupt_payload(target, entries):
        for item, payload in entries:
            if item.filename.endswith("record.md"):
                payload = b"changed"
            target.writestr(item, payload)
    _rewrite(corrupted, corrupt_payload)
    assert any("mismatch" in issue for issue in verify_snapshot(corrupted)["issues"])

    missing = Path(create_snapshot(project, tmp_path / "missing")["snapshot"])
    _rewrite(missing, lambda target, entries: [target.writestr(item, payload) for item, payload in entries if not item.filename.endswith("record.md")])
    assert any("missing file" in issue for issue in verify_snapshot(missing)["issues"])

    extra = Path(create_snapshot(project, tmp_path / "extra")["snapshot"])
    def add_extra(target, entries):
        for item, payload in entries:
            target.writestr(item, payload)
        target.writestr("workspace/extra.txt", b"extra")
    _rewrite(extra, add_extra)
    assert any("extra file" in issue for issue in verify_snapshot(extra)["issues"])

    manifest_tamper = Path(create_snapshot(project, tmp_path / "manifest")["snapshot"])
    def tamper_manifest(target, entries):
        for item, payload in entries:
            target.writestr(item, payload + b"\n# tampered" if item.filename == "manifest.yaml" else payload)
    _rewrite(manifest_tamper, tamper_manifest)
    assert any("manifest hash mismatch" in issue for issue in verify_snapshot(manifest_tamper)["issues"])


def test_snapshot_rejects_path_traversal(rf_env, tmp_path):
    project = _project(rf_env)
    snapshot = Path(create_snapshot(project, tmp_path / "backups")["snapshot"])
    def add_traversal(target, entries):
        for item, payload in entries:
            target.writestr(item, payload)
        target.writestr("workspace/../../escape.txt", b"no")
    _rewrite(snapshot, add_traversal)
    result = verify_snapshot(snapshot)
    assert result["valid"] is False
    assert "unsafe path" in result["issues"][0]


def test_snapshot_rejects_rehashed_malformed_manifest(rf_env, tmp_path):
    project = _project(rf_env)
    snapshot = Path(create_snapshot(project, tmp_path / "backups")["snapshot"])
    _rewrite_manifest(snapshot, lambda manifest: manifest.pop("created_at"))
    result = verify_snapshot(snapshot)
    assert result["valid"] is False
    assert any("created_at" in issue for issue in result["issues"])
    with pytest.raises(ResearchFlowError, match="verification failed"):
        restore_snapshot(project, snapshot, target=tmp_path / "restore")


def test_snapshot_shared_directory_remains_project_scoped(rf_env, tmp_path, capsys):
    project = _project(rf_env)
    other_root = add_project("other", rf_env["repo"])
    other = ResearchProject.open("other")
    shared = tmp_path / "shared"
    own_snapshot = Path(create_snapshot(project, shared)["snapshot"])
    other_snapshot = Path(create_snapshot(other, shared)["snapshot"])
    assert [Path(item["path"]) for item in list_snapshots(project, shared)] == [own_snapshot]

    from researchflow.cli import main
    assert main(["--project", "toy", "snapshot", "verify", str(other_snapshot)]) == 1
    assert "not selected project toy" in capsys.readouterr().out
    assert other_root.exists()


def test_snapshot_restore_new_target_dry_run_and_in_place_backup(rf_env, tmp_path):
    project = _project(rf_env)
    state = project.root / "memory" / "current-state.md"
    original = state.read_text(encoding="utf-8")
    snapshot = Path(create_snapshot(project, tmp_path / "backups")["snapshot"])

    dry_target = tmp_path / "dry-target"
    dry = restore_snapshot(project, snapshot, target=dry_target, dry_run=True)
    assert dry["dry_run"] is True
    assert not dry_target.exists()

    nested_target = project.root / "restore-copy"
    with pytest.raises(ResearchFlowError, match="outside the live project workspace"):
        restore_snapshot(project, snapshot, target=nested_target, dry_run=True)
    assert not nested_target.exists()

    target = tmp_path / "新恢复目录"
    restored = restore_snapshot(project, snapshot, target=target)
    assert restored["restored"] is True
    assert (target / "memory" / "current-state.md").read_text(encoding="utf-8") == original
    with pytest.raises(ResearchFlowError, match="already exists"):
        restore_snapshot(project, snapshot, target=target)

    state.write_text("damaged\n", encoding="utf-8")
    with pytest.raises(ResearchFlowError, match="--in-place --yes"):
        restore_snapshot(project, snapshot, in_place=True)
    result = restore_snapshot(project, snapshot, in_place=True, yes=True)
    assert state.read_text(encoding="utf-8") == original
    backup = Path(result["backup"])
    assert (backup / "memory" / "current-state.md").read_text(encoding="utf-8") == "damaged\n"
