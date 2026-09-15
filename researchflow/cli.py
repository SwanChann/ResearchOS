from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from .config import configure_zotero, init_config, load_config, save_config
from .daily import create_daily_log
from .doctor import run_doctor
from .errors import ResearchFlowError
from .project import ResearchProject, add_project, list_projects, project_path
from .records import add_decision, add_hypothesis, add_observation, show_record


def csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _configure_utf8_output(streams: tuple[Any, ...] | None = None, platform: str | None = None) -> None:
    """Keep redirected Windows CLI output lossless for Unicode research metadata."""
    if (platform or sys.platform) != "win32":
        return
    for stream in streams or (sys.stdout, sys.stderr):
        if stream is None or stream.isatty():
            continue
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("_", "-")
        reconfigure = getattr(stream, "reconfigure", None)
        if encoding in {"utf-8", "utf8"} or not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            # Some embedded streams cannot be reconfigured. Preserve the
            # existing stream rather than making every CLI command fail.
            pass


def choose_project(project_id: str | None) -> ResearchProject:
    config = load_config()
    candidate = project_id or config.get("default_project")
    if not candidate:
        projects = list_projects(config)
        if len(projects) == 1:
            candidate = projects[0]
        else:
            raise ResearchFlowError("Project is ambiguous. Pass --project <id> or set default_project in config.yaml.")
    return ResearchProject.open(candidate, config)


def dump(value: Any) -> None:
    if isinstance(value, str):
        print(value)
    else:
        print(yaml.safe_dump(value, sort_keys=False, allow_unicode=True).rstrip())


def project_summary(selected: ResearchProject) -> dict[str, Any]:
    from .gitops import inspect_git_state
    from .snapshot import default_snapshot_dir, list_snapshots
    summary = dict(selected.data)
    summary["workspace"] = str(selected.root)
    summary["independent_repo"] = str(selected.repo)
    summary["repo_state"] = inspect_git_state(selected.repo).as_dict()
    summary["startup_files"] = [
        str(selected.root / "AGENTS.md"),
        str(selected.root / "KNOWLEDGE.md"),
        str(selected.root / "memory" / "current-state.md"),
    ]
    snapshots = [item for item in list_snapshots(selected) if item.get("valid")]
    summary["recovery"] = {
        "snapshot_count": len(snapshots),
        "default_snapshot_directory": str(default_snapshot_dir(selected)),
        "git_checkpoint_available": summary["repo_state"]["recoverable_checkpoint"],
        "external_assets_backed_up": False,
    }
    summary["authority_boundary"] = (
        "ResearchFlow workspace and independent repo are separate authorities; snapshots cover workspace records only by default."
    )
    summary["explicit_project_command"] = f"rf --project {selected.data['id']} status"
    return summary


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="rf", description="Local-first Research OS")
    root.add_argument("--project", help="project ID (or use the configured default)")
    # Keep the top-level route separate from leaf options such as
    # `experiment new --command` and `compute plan --command`.
    commands = root.add_subparsers(dest="root_command", required=True)

    init = commands.add_parser("init", help="initialize global ResearchFlow configuration")
    init.add_argument("--home", type=Path, default=Path.home() / "ResearchFlow")
    init.add_argument("--force", action="store_true")

    project = commands.add_parser("project", help="manage project workspaces")
    project_actions = project.add_subparsers(dest="action", required=True)
    add = project_actions.add_parser("add")
    add.add_argument("id")
    add.add_argument("--repo", required=True, type=Path)
    add.add_argument("--name")
    project_actions.add_parser("list")
    show = project_actions.add_parser("show")
    show.add_argument("id", nargs="?")

    snapshot = commands.add_parser("snapshot", help="create, verify, and restore project workspace snapshots")
    snapshot_actions = snapshot.add_subparsers(dest="action", required=True)
    snapshot_create = snapshot_actions.add_parser("create")
    snapshot_create.add_argument("--output-dir", type=Path)
    snapshot_create.add_argument(
        "--include-redacted-config", action="store_true",
        help="include a redacted config export; raw secrets are never included",
    )
    snapshot_list = snapshot_actions.add_parser("list")
    snapshot_list.add_argument("--input-dir", type=Path)
    snapshot_show = snapshot_actions.add_parser("show")
    snapshot_show.add_argument("snapshot", type=Path)
    snapshot_verify = snapshot_actions.add_parser("verify")
    snapshot_verify.add_argument("snapshot", type=Path)
    snapshot_restore = snapshot_actions.add_parser("restore")
    snapshot_restore.add_argument("snapshot", type=Path)
    snapshot_restore.add_argument("--target", type=Path)
    snapshot_restore.add_argument("--in-place", action="store_true")
    snapshot_restore.add_argument("--yes", action="store_true")
    snapshot_restore.add_argument("--dry-run", action="store_true")

    status = commands.add_parser("status", help="show current state computed from project contracts and registries")
    status.add_argument("--verbose", action="store_true")

    evidence = commands.add_parser("evidence", help="manage literature and code evidence")
    evidence_actions = evidence.add_subparsers(dest="evidence_kind", required=True)
    for kind in ("paper", "repo"):
        group = evidence_actions.add_parser(kind)
        actions = group.add_subparsers(dest="action", required=True)
        add_e = actions.add_parser("add")
        if kind == "paper":
            add_e.add_argument("pdf", type=Path)
            add_e.add_argument("--title", required=True)
            add_e.add_argument("--authors")
            add_e.add_argument("--venue")
            add_e.add_argument("--year", type=int)
            add_e.add_argument("--url")
        else:
            add_e.add_argument("--name", required=True)
            add_e.add_argument("--commit", required=True)
            add_e.add_argument("--url")
            add_e.add_argument("--local", type=Path)
            add_e.add_argument("--papers")
            add_e.add_argument("--notes", default="")
        add_e.add_argument("--tags")
        actions.add_parser("list")
        show_e = actions.add_parser("show")
        show_e.add_argument("id")
        if kind == "paper":
            verify_e = actions.add_parser("verify", help="finalize a page-cited primary-source deep read")
            verify_e.add_argument("id")
            verify_e.add_argument("--sha256", required=True)
            verify_e.add_argument("--source-version", required=True)
            verify_e.add_argument("--pages", required=True, type=int)
            verify_e.add_argument("--core-operator", required=True)
            verify_e.add_argument("--primary-logic", required=True)
            verify_e.add_argument("--methods", required=True)
            review_e = actions.add_parser("review", help="record a scoped human semantic review")
            review_e.add_argument("id")
            review_e.add_argument("--reviewer", required=True)
            review_e.add_argument("--decision", choices=("accepted", "revision_requested", "rejected"), required=True)
            review_e.add_argument("--scope", required=True)
            review_e.add_argument("--notes")
            review_e.add_argument("--notes-path", type=Path)
        if kind == "repo":
            search_e = actions.add_parser("search")
            search_e.add_argument("query")
    matrix = evidence_actions.add_parser("matrix", help="manage the structured cross-paper literature matrix")
    matrix_actions = matrix.add_subparsers(dest="action", required=True)
    matrix_init = matrix_actions.add_parser("init")
    matrix_init.add_argument("--title", required=True)
    matrix_init.add_argument("--scope", required=True)
    matrix_init.add_argument("--template", default="generic")
    matrix_init.add_argument("--axes-file", type=Path)
    matrix_templates = matrix_actions.add_parser("templates")
    matrix_template_actions = matrix_templates.add_subparsers(dest="template_action", required=True)
    matrix_template_actions.add_parser("list")
    matrix_template_show = matrix_template_actions.add_parser("show")
    matrix_template_show.add_argument("template")
    matrix_axes = matrix_actions.add_parser("axes")
    matrix_axes_actions = matrix_axes.add_subparsers(dest="axes_action", required=True)
    matrix_axes_scaffold = matrix_axes_actions.add_parser("scaffold")
    matrix_axes_scaffold.add_argument("path", type=Path)
    matrix_axes_scaffold.add_argument("--template", default="generic")
    matrix_axes_validate = matrix_axes_actions.add_parser("validate")
    matrix_axes_validate.add_argument("path", type=Path)
    matrix_axes_confirm = matrix_axes_actions.add_parser("confirm")
    matrix_axes_confirm.add_argument("path", type=Path)
    matrix_actions.add_parser("validate")
    matrix_add = matrix_actions.add_parser("add")
    matrix_add.add_argument("entry", type=Path, help="YAML entry containing one verified paper and every matrix axis")
    matrix_synthesize = matrix_actions.add_parser("synthesize")
    matrix_synthesize.add_argument(
        "update", type=Path, help="YAML update containing evidence-linked cross-paper syntheses and ideas"
    )
    matrix_migrate = matrix_actions.add_parser("migrate")
    matrix_migrate.add_argument("migration", type=Path)
    matrix_migrate.add_argument("--dry-run", action="store_true")
    matrix_actions.add_parser("render")
    matrix_actions.add_parser("show")
    matrix_review = matrix_actions.add_parser("review", help="record a scoped human semantic review")
    matrix_review.add_argument("--reviewer", required=True)
    matrix_review.add_argument("--decision", choices=("accepted", "revision_requested", "rejected"), required=True)
    matrix_review.add_argument("--scope", required=True)
    matrix_review.add_argument("--notes")
    matrix_review.add_argument("--notes-path", type=Path)
    for kind in ("problem", "claim"):
        group = evidence_actions.add_parser(kind, help=f"manage formal {kind} records")
        actions = group.add_subparsers(dest="action", required=True)
        add_record = actions.add_parser("add")
        add_record.add_argument("request", type=Path)
        add_record.add_argument("--dry-run", action="store_true")
        actions.add_parser("list")
        show_record_parser = actions.add_parser("show")
        show_record_parser.add_argument("id")
        if kind == "claim":
            supersede_record = actions.add_parser("supersede")
            supersede_record.add_argument("id")
            supersede_record.add_argument("--with", required=True, dest="replacement", type=Path)
            supersede_record.add_argument("--dry-run", action="store_true")
    corpus = evidence_actions.add_parser("corpus", help="freeze and review a verified paper corpus")
    corpus_actions = corpus.add_subparsers(dest="action", required=True)
    corpus_create = corpus_actions.add_parser("create")
    corpus_create.add_argument("--matrix", required=True)
    corpus_create.add_argument("--title", required=True)
    corpus_create.add_argument("--scope-file", required=True, type=Path)
    corpus_create.add_argument("--created-by", default="agent")
    corpus_create.add_argument("--supersedes")
    corpus_create.add_argument("--dry-run", action="store_true")
    corpus_actions.add_parser("list")
    corpus_show = corpus_actions.add_parser("show")
    corpus_show.add_argument("id")
    corpus_verify = corpus_actions.add_parser("verify")
    corpus_verify.add_argument("id")
    corpus_status = corpus_actions.add_parser("status")
    corpus_status.add_argument("id")
    corpus_extract = corpus_actions.add_parser("add-extraction")
    corpus_extract.add_argument("request", type=Path)
    corpus_extract.add_argument("--dry-run", action="store_true")
    corpus_review = corpus_actions.add_parser("review-extraction")
    corpus_review.add_argument("--corpus", required=True)
    corpus_review.add_argument("--paper", required=True)
    corpus_review.add_argument("--decision", choices=("accepted", "revision_requested", "rejected"), required=True)
    corpus_review.add_argument("--reviewer", required=True)
    corpus_review.add_argument("--rationale-file", required=True, type=Path)
    corpus_review.add_argument("--dry-run", action="store_true")
    gap = evidence_actions.add_parser("gap", help="derive and human-review deterministic Gap candidates")
    gap_actions = gap.add_subparsers(dest="action", required=True)
    gap_detect = gap_actions.add_parser("detect")
    gap_detect.add_argument("--corpus", required=True)
    gap_detect.add_argument("--motifs", required=True, type=Path)
    gap_detect.add_argument("--test-only", action="store_true")
    gap_detect.add_argument("--dry-run", action="store_true")
    gap_list = gap_actions.add_parser("list")
    gap_list.add_argument("--state", choices=("candidate", "approved", "rejected", "superseded"))
    gap_show = gap_actions.add_parser("show")
    gap_show.add_argument("id")
    gap_review = gap_actions.add_parser("review")
    gap_review.add_argument("id")
    gap_review.add_argument("--decision", choices=("approve", "reject"), required=True)
    gap_review.add_argument("--reviewer", required=True)
    gap_review.add_argument("--rationale-file", required=True, type=Path)
    gap_review.add_argument("--dry-run", action="store_true")
    adjacency = evidence_actions.add_parser("adjacency", help="build and review evidence-bound PAPER-to-PAPER relationships")
    adjacency_actions = adjacency.add_subparsers(dest="action", required=True)
    adjacency_build = adjacency_actions.add_parser("build", help="derive deterministic candidates from accepted Corpus extractions")
    adjacency_build.add_argument("--corpus", required=True)
    adjacency_build.add_argument("--dry-run", action="store_true")
    adjacency_add = adjacency_actions.add_parser("add", help="import an evidence-bound manual or agent-proposed adjacency")
    adjacency_add.add_argument("request", type=Path)
    adjacency_add.add_argument("--dry-run", action="store_true")
    adjacency_list = adjacency_actions.add_parser("list")
    adjacency_list.add_argument("--status", choices=("candidate", "accepted", "revision_requested", "rejected"))
    adjacency_list.add_argument("--corpus")
    adjacency_show = adjacency_actions.add_parser("show")
    adjacency_show.add_argument("id")
    adjacency_neighbors = adjacency_actions.add_parser("neighbors")
    adjacency_neighbors.add_argument("paper_id")
    adjacency_neighbors.add_argument("--status", choices=("candidate", "accepted", "revision_requested", "rejected", "all"), default="accepted")
    adjacency_neighbors.add_argument("--top-k", type=int, default=10)
    adjacency_explain = adjacency_actions.add_parser("explain")
    adjacency_explain.add_argument("source")
    adjacency_explain.add_argument("target")
    adjacency_review = adjacency_actions.add_parser("review")
    adjacency_review.add_argument("id")
    adjacency_review.add_argument("--decision", choices=("accepted", "revision_requested", "rejected"), required=True)
    adjacency_review.add_argument("--reviewer", required=True)
    adjacency_review.add_argument("--rationale-file", required=True, type=Path)
    adjacency_review.add_argument("--dry-run", action="store_true")
    adjacency_actions.add_parser("check")
    adjacency_export = adjacency_actions.add_parser("export")
    adjacency_export.add_argument("--output", required=True, type=Path)
    adjacency_export.add_argument("--format", choices=("dot", "json"), default="json")
    adjacency_export.add_argument("--dry-run", action="store_true")
    adjacency_promote = adjacency_actions.add_parser("promote", help="copy one accepted adjacency into EvidenceGraph with PADJ provenance")
    adjacency_promote.add_argument("id")
    adjacency_promote.add_argument("--dry-run", action="store_true")
    graph = evidence_actions.add_parser("graph", help="manage the rebuildable project EvidenceGraph")
    graph_actions = graph.add_subparsers(dest="action", required=True)
    graph_connect = graph_actions.add_parser("connect", help="add one typed, fingerprint-bound relationship")
    graph_connect.add_argument("--from", required=True, dest="source")
    graph_connect.add_argument("--relation", required=True)
    graph_connect.add_argument("--to", required=True, dest="target")
    graph_connect.add_argument("--provenance")
    graph_connect.add_argument("--dry-run", action="store_true")
    graph_rebuild = graph_actions.add_parser("rebuild", help="regenerate the non-authoritative graph index")
    graph_rebuild.add_argument("--dry-run", action="store_true")
    graph_check = graph_actions.add_parser("check", help="run deterministic graph and evidence checks")
    graph_check.add_argument("--strict", action="store_true", help="also fail when semantic review is pending")
    graph_show = graph_actions.add_parser("show")
    graph_show.add_argument("--claim", required=True)
    graph_audit = graph_actions.add_parser("audit")
    graph_audit.add_argument("--claim", required=True)
    graph_audit.add_argument("--mode", choices=("full-chain",), default="full-chain")
    graph_audit.add_argument("--dry-run", action="store_true")
    graph_review = graph_actions.add_parser("review", help="import a fingerprint-bound L2/L3 review file")
    graph_review.add_argument("--claim", required=True)
    graph_review.add_argument("--file", required=True, type=Path)
    graph_review.add_argument("--dry-run", action="store_true")
    graph_review_input = graph_actions.add_parser("review-input", help="show the current review input fingerprint")
    graph_review_input.add_argument("--claim", required=True)
    graph_export = graph_actions.add_parser("export", help="export a derived DOT or JSON graph view")
    graph_export.add_argument("--output", required=True, type=Path)
    graph_export.add_argument("--format", choices=("dot", "json"), default="dot")
    graph_export.add_argument("--dry-run", action="store_true")
    search = evidence_actions.add_parser("search")
    search.add_argument("query")
    zotero = evidence_actions.add_parser("zotero", help="read from the Zotero-owned literature library")
    zotero_actions = zotero.add_subparsers(dest="action", required=True)
    zotero_configure = zotero_actions.add_parser("configure")
    zotero_configure.add_argument("--base-url", default="http://127.0.0.1:23119/api")
    zotero_configure.add_argument("--library", default="users/0")
    zotero_status = zotero_actions.add_parser("status")
    zotero_status.add_argument("--verbose", action="store_true")
    zotero_doctor = zotero_actions.add_parser("doctor")
    zotero_doctor.add_argument("--item-key")
    zotero_actions.add_parser("libraries")
    zotero_collections = zotero_actions.add_parser("collections")
    zotero_collections.add_argument("--library")
    zotero_search = zotero_actions.add_parser("search")
    zotero_search.add_argument("query")
    zotero_search.add_argument("--library")
    zotero_search.add_argument("--collection")
    zotero_search.add_argument("--tag")
    zotero_search.add_argument("--limit", type=int, default=25)
    zotero_show = zotero_actions.add_parser("show")
    zotero_show.add_argument("item_key")
    zotero_show.add_argument("--library")
    zotero_link = zotero_actions.add_parser("link")
    zotero_link.add_argument("item_key")
    zotero_link.add_argument("--library")
    zotero_refresh = zotero_actions.add_parser("refresh")
    zotero_refresh.add_argument("paper_id")
    zotero_bib = zotero_actions.add_parser("bibliography")
    zotero_bib.add_argument("item_keys", nargs="+")
    zotero_bib.add_argument("--library")
    zotero_bib.add_argument("--style", default="apa")
    zotero_bib.add_argument("--locale", default="en-US")

    memory = commands.add_parser("memory", help="manage observations and decisions")
    memory_types = memory.add_subparsers(dest="memory_kind", required=True)
    observation = memory_types.add_parser("observation")
    observation_actions = observation.add_subparsers(dest="action", required=True)
    obs_add = observation_actions.add_parser("add")
    obs_add.add_argument("--title", required=True)
    obs_add.add_argument("--text", required=True)
    obs_add.add_argument("--evidence")
    obs_add.add_argument("--confidence", choices=("low", "medium", "high"), default="medium")
    obs_show = observation_actions.add_parser("show")
    obs_show.add_argument("id")
    decision = memory_types.add_parser("decision")
    decision_actions = decision.add_subparsers(dest="action", required=True)
    dec_add = decision_actions.add_parser("add")
    dec_add.add_argument("--text", required=True)
    dec_add.add_argument("--why", required=True)
    dec_add.add_argument("--evidence", required=True)
    dec_show = decision_actions.add_parser("show")
    dec_show.add_argument("id")

    artifact = commands.add_parser("artifact", help="register and integrity-check project research products")
    artifact_actions = artifact.add_subparsers(dest="action", required=True)
    artifact_add = artifact_actions.add_parser("add")
    artifact_add.add_argument("path", type=Path)
    artifact_add.add_argument("--title", required=True)
    artifact_add.add_argument("--type", required=True, dest="artifact_type")
    artifact_add.add_argument("--status", choices=("draft", "active", "verified"), default="draft")
    artifact_add.add_argument("--authority", default="researchflow_workspace")
    artifact_add.add_argument("--derived-from")
    artifact_add.add_argument("--evidence")
    artifact_add.add_argument("--schema")
    artifact_add.add_argument("--version")
    artifact_list = artifact_actions.add_parser("list")
    artifact_list.add_argument("--status", choices=("draft", "active", "verified", "superseded"))
    artifact_show = artifact_actions.add_parser("show")
    artifact_show.add_argument("id")
    artifact_verify = artifact_actions.add_parser("verify")
    artifact_verify.add_argument("id", nargs="?")
    artifact_refresh = artifact_actions.add_parser("refresh")
    artifact_refresh.add_argument("id")
    artifact_supersede = artifact_actions.add_parser("supersede")
    artifact_supersede.add_argument("id")
    artifact_supersede.add_argument("--by", required=True)
    artifact_migrate = artifact_actions.add_parser("migrate")
    artifact_migrate.add_argument("--scan", required=True, type=Path)
    artifact_migrate.add_argument("--dry-run", action="store_true")

    knowledge = commands.add_parser("knowledge", help="rebuild and check the generated KNOWLEDGE navigation region")
    knowledge_actions = knowledge.add_subparsers(dest="action", required=True)
    knowledge_rebuild = knowledge_actions.add_parser("rebuild")
    knowledge_rebuild.add_argument("--dry-run", action="store_true")
    knowledge_actions.add_parser("check")

    scaffold = commands.add_parser("scaffold", help="create contract-oriented agent draft files")
    scaffold_actions = scaffold.add_subparsers(dest="scaffold_kind", required=True)
    scaffold_paper = scaffold_actions.add_parser("paper-analysis")
    scaffold_paper.add_argument("paper_id")
    scaffold_paper.add_argument("--output", required=True, type=Path)
    scaffold_entry = scaffold_actions.add_parser("matrix-entry")
    scaffold_entry.add_argument("paper_id")
    scaffold_entry.add_argument("--output", required=True, type=Path)
    scaffold_synthesis = scaffold_actions.add_parser("synthesis-idea")
    scaffold_synthesis.add_argument("--output", required=True, type=Path)
    scaffold_artifact = scaffold_actions.add_parser("artifact")
    scaffold_artifact.add_argument("--path", required=True, type=Path)
    scaffold_artifact.add_argument("--title", required=True)
    scaffold_artifact.add_argument("--type", required=True, dest="artifact_type")
    scaffold_artifact.add_argument("--output", required=True, type=Path)
    scaffold_problem = scaffold_actions.add_parser("problem")
    scaffold_problem.add_argument("--output", required=True, type=Path)
    scaffold_claim = scaffold_actions.add_parser("claim")
    scaffold_claim.add_argument("--output", required=True, type=Path)
    scaffold_extraction = scaffold_actions.add_parser("corpus-extraction")
    scaffold_extraction.add_argument("--corpus", required=True)
    scaffold_extraction.add_argument("--paper", required=True)
    scaffold_extraction.add_argument("--output", required=True, type=Path)
    scaffold_graph_review = scaffold_actions.add_parser("graph-review")
    scaffold_graph_review.add_argument("--claim", required=True)
    scaffold_graph_review.add_argument("--output", required=True, type=Path)
    scaffold_adjacency = scaffold_actions.add_parser("paper-adjacency")
    scaffold_adjacency.add_argument("--corpus", required=True)
    scaffold_adjacency.add_argument("--from", required=True, dest="source")
    scaffold_adjacency.add_argument("--to", required=True, dest="target")
    scaffold_adjacency.add_argument("--output", required=True, type=Path)

    preflight = commands.add_parser("preflight", help="validate a draft before a formal atomic write")
    preflight.add_argument(
        "kind", choices=("paper-analysis", "matrix-entry", "matrix-synthesis", "artifact", "problem", "claim", "corpus-extraction", "paper-adjacency", "graph-review")
    )
    preflight.add_argument("path", type=Path)

    migrate = commands.add_parser("migrate", help="run explicit, previewable project record migrations")
    migrate_actions = migrate.add_subparsers(dest="migration_kind", required=True)
    migrate_paper = migrate_actions.add_parser("paper-verification")
    migrate_paper.add_argument("--dry-run", action="store_true")
    migrate_graph = migrate_actions.add_parser("corpus-gap-evidence-graph")
    migrate_graph.add_argument("--dry-run", action="store_true")
    migrate_graph.add_argument("--plan-fingerprint")
    migrate_graph.add_argument("--snapshot-dir", type=Path)

    hypothesis = commands.add_parser("hypothesis", help="manage falsifiable hypotheses")
    hypothesis_actions = hypothesis.add_subparsers(dest="action", required=True)
    hyp_new = hypothesis_actions.add_parser("new")
    hyp_new.add_argument("--title", required=True)
    hyp_new.add_argument("--statement", required=True)
    hyp_new.add_argument("--observations")
    hyp_new.add_argument("--papers")
    hyp_new.add_argument("--ideas", help="comma-separated formal XIDEA IDs from the current literature matrix")
    hyp_new.add_argument("--gap", dest="gaps", help="comma-separated human-approved GAP IDs")
    hyp_new.add_argument("--falsification", required=True)
    hyp_show = hypothesis_actions.add_parser("show")
    hyp_show.add_argument("id")

    # Lifecycle commands are attached by their modules to keep this public tree stable.
    from .experiments import add_experiment_parser
    from .runs import add_run_parser
    from .compute import add_compute_parser
    add_experiment_parser(commands)
    add_run_parser(commands)
    add_compute_parser(commands)

    commands.add_parser("daily", help="write a decision-relevant daily log")
    doctor = commands.add_parser("doctor", help="check configuration and project integrity")
    doctor.add_argument(
        "--probe-machines",
        action="store_true",
        help="explicitly perform live local/SSH machine probes (may contact remote hosts)",
    )
    doctor.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero for WARN as well as FAIL; ordinary warnings retain exit code 0",
    )
    return root


def execute(args: argparse.Namespace) -> int:
    if args.root_command == "init":
        print(f"Initialized: {init_config(args.home, force=args.force)}")
        return 0
    if args.root_command == "project":
        if args.action == "add":
            workspace = add_project(args.id, args.repo, args.name)
            config = load_config()
            if not config.get("default_project"):
                config["default_project"] = args.id
                save_config(config)
            selected = ResearchProject.open(args.id, config)
            result = project_summary(selected)
            result["created_workspace"] = str(workspace)
            result["notice"] = "No Git commit or snapshot was created automatically."
            dump(result)
        elif args.action == "list":
            print("\n".join(list_projects()) or "No projects.")
        else:
            selected = choose_project(args.id or args.project)
            dump(project_summary(selected))
        return 0
    project_commands = {"status", "snapshot", "evidence", "memory", "artifact", "knowledge", "scaffold", "preflight", "migrate", "hypothesis", "experiment", "run", "daily"}
    project = choose_project(args.project) if args.root_command in project_commands else None
    if args.root_command == "status":
        dump(project.status(verbose=args.verbose))
    elif args.root_command == "snapshot":
        from .snapshot import create_snapshot, list_snapshots, restore_snapshot, show_snapshot, verify_snapshot
        if args.action == "create":
            dump(create_snapshot(project, args.output_dir, include_redacted_config=args.include_redacted_config))
        elif args.action == "list":
            dump(list_snapshots(project, args.input_dir))
        elif args.action == "show":
            dump(show_snapshot(args.snapshot))
        elif args.action == "verify":
            result = verify_snapshot(args.snapshot, expected_project_id=project.data["id"])
            dump(result)
            return 0 if result["valid"] else 1
        else:
            dump(restore_snapshot(
                project, args.snapshot, target=args.target, in_place=args.in_place,
                yes=args.yes, dry_run=args.dry_run,
            ))
    elif args.root_command == "evidence":
        store = project.evidence
        if args.evidence_kind == "search":
            dump(store.search(args.query))
        elif args.evidence_kind == "matrix":
            from .literature import (
                MATRIX_TEMPLATES, LiteratureMatrixStore, axes_template, confirm_axes,
                load_axes_file, scaffold_axes,
            )
            matrix_store = LiteratureMatrixStore(project)
            if args.action == "init":
                print(matrix_store.initialize(args.title, args.scope, template=args.template, axes_file=args.axes_file))
            elif args.action == "templates":
                if args.template_action == "list":
                    dump([{
                        "name": name,
                        "version": value["version"],
                        "description": value["description"],
                        "axes": len(value["axes"]),
                    } for name, value in sorted(MATRIX_TEMPLATES.items())])
                else:
                    dump(axes_template(args.template))
            elif args.action == "axes":
                if args.axes_action == "scaffold":
                    print(scaffold_axes(args.path, args.template))
                elif args.axes_action == "validate":
                    dump(load_axes_file(args.path, allow_draft=True))
                else:
                    print(confirm_axes(args.path))
            elif args.action == "validate":
                dump(matrix_store.validate())
            elif args.action == "add":
                print(matrix_store.add_entry_file(args.entry))
            elif args.action == "synthesize":
                dump(matrix_store.synthesize_file(args.update))
            elif args.action == "migrate":
                dump(matrix_store.migrate_axes_file(args.migration, dry_run=args.dry_run))
            elif args.action == "render":
                print(matrix_store.render())
            elif args.action == "review":
                from .review import add_matrix_review
                dump(add_matrix_review(
                    matrix_store, reviewer=args.reviewer, decision=args.decision, scope=args.scope,
                    notes=args.notes, notes_path=args.notes_path,
                ))
            else:
                from .review import matrix_review_status
                record = matrix_store.load()
                dump({"record": record, "review_status": matrix_review_status(record)})
        elif args.evidence_kind == "zotero":
            from .zotero import ZoteroClient, diagnose_zotero, zotero_settings
            if args.action == "configure":
                dump(configure_zotero(args.base_url, args.library))
                return 0
            if args.action == "doctor" or (args.action == "status" and args.verbose):
                result = diagnose_zotero(project, item_key=getattr(args, "item_key", None))
                dump(result)
                return 0 if result["healthy"] else 1
            settings = zotero_settings()
            client = ZoteroClient(settings["base_url"], getattr(args, "library", None) or settings["library"])
            if args.action == "status":
                dump({"authority": settings["authority"], **client.status()})
            elif args.action == "libraries":
                dump(client.libraries())
            elif args.action == "collections":
                dump(client.collections())
            elif args.action == "search":
                dump(client.search(args.query, args.collection, args.tag, args.limit))
            elif args.action == "show":
                dump(client.context(args.item_key))
            elif args.action == "link":
                print(store.link_zotero(client, args.item_key))
            elif args.action == "refresh":
                source = store.show(args.paper_id)["metadata"].get("source", {}).get("zotero", {})
                refresh_client = ZoteroClient(settings["base_url"], source.get("library", settings["library"]))
                print(store.refresh_zotero(args.paper_id, refresh_client))
            else:
                print(client.bibliography(args.item_keys, args.style, args.locale))
        elif args.evidence_kind == "corpus":
            from .corpus_gap import CorpusStore
            corpora = CorpusStore(project)
            if args.action == "create":
                dump(corpora.create(
                    title=args.title, matrix_id=args.matrix, scope_file=args.scope_file,
                    created_by=args.created_by, supersedes=args.supersedes, dry_run=args.dry_run,
                ))
            elif args.action == "list":
                dump(corpora.list())
            elif args.action == "show":
                dump(corpora.show(args.id))
            elif args.action == "verify":
                result = corpora.verify(args.id)
                dump(result)
                return 0 if result["valid"] else 1
            elif args.action == "status":
                dump(corpora.extraction_status(args.id))
            elif args.action == "add-extraction":
                dump(corpora.add_extraction(args.request, dry_run=args.dry_run))
            else:
                rationale = args.rationale_file.expanduser().resolve().read_text(encoding="utf-8")
                dump(corpora.review_extraction(
                    args.corpus, args.paper, decision=args.decision, reviewer=args.reviewer,
                    rationale=rationale, dry_run=args.dry_run,
                ))
        elif args.evidence_kind == "gap":
            from .corpus_gap import GapStore
            gaps = GapStore(project)
            if args.action == "detect":
                dump(gaps.detect(args.corpus, args.motifs, dry_run=args.dry_run, test_only=args.test_only))
            elif args.action == "list":
                dump(gaps.list(args.state))
            elif args.action == "show":
                dump(gaps.show(args.id))
            else:
                rationale = args.rationale_file.expanduser().resolve().read_text(encoding="utf-8")
                dump(gaps.review(
                    args.id, decision=args.decision, reviewer=args.reviewer,
                    rationale=rationale, dry_run=args.dry_run,
                ))
        elif args.evidence_kind == "adjacency":
            from .adjacency import PaperAdjacencyStore
            adjacency_store = PaperAdjacencyStore(project)
            if args.action == "build":
                dump(adjacency_store.build(args.corpus, dry_run=args.dry_run))
            elif args.action == "add":
                dump(adjacency_store.add_file(args.request, dry_run=args.dry_run))
            elif args.action == "list":
                dump(adjacency_store.list(status=args.status, corpus_id=args.corpus))
            elif args.action == "show":
                dump(adjacency_store.show(args.id))
            elif args.action == "neighbors":
                dump(adjacency_store.neighbors(args.paper_id, status=args.status, top_k=args.top_k))
            elif args.action == "explain":
                dump(adjacency_store.explain(args.source, args.target))
            elif args.action == "review":
                rationale = args.rationale_file.expanduser().resolve().read_text(encoding="utf-8")
                dump(adjacency_store.review(
                    args.id, decision=args.decision, reviewer=args.reviewer,
                    rationale=rationale, dry_run=args.dry_run,
                ))
            elif args.action == "check":
                result = adjacency_store.check()
                dump(result)
                return 0 if result["valid"] else 1
            elif args.action == "promote":
                dump(adjacency_store.promote(args.id, dry_run=args.dry_run))
            else:
                dump(adjacency_store.export(args.output, format=args.format, dry_run=args.dry_run))
        elif args.evidence_kind in {"problem", "claim"}:
            from .evidence_graph import ClaimStore, ProblemStore
            records = ProblemStore(project) if args.evidence_kind == "problem" else ClaimStore(project)
            if args.action == "add":
                dump(records.add_file(args.request, dry_run=args.dry_run))
            elif args.action == "supersede":
                dump(records.supersede_file(args.id, args.replacement, dry_run=args.dry_run))
            elif args.action == "list":
                dump(records.list())
            else:
                dump(records.show(args.id))
        elif args.evidence_kind == "graph":
            from .evidence_graph import EvidenceGraphStore
            graph_store = EvidenceGraphStore(project)
            if args.action == "connect":
                dump(graph_store.connect(
                    args.source, args.relation, args.target,
                    provenance_refs=csv(args.provenance), dry_run=args.dry_run,
                ))
            elif args.action == "rebuild":
                dump(graph_store.rebuild(dry_run=args.dry_run))
            elif args.action == "check":
                result = graph_store.check()
                dump(result)
                return 0 if result["valid"] and (not args.strict or result["ready"]) else 1
            elif args.action == "show":
                dump(graph_store.claim_view(args.claim))
            elif args.action == "audit":
                dump(graph_store.audit(args.claim, dry_run=args.dry_run))
            elif args.action == "review":
                dump(graph_store.import_review(args.claim, args.file, dry_run=args.dry_run))
            elif args.action == "review-input":
                dump({"claim_id": args.claim, "input_fingerprint": graph_store.review_input_fingerprint(args.claim)})
            else:
                dump(graph_store.export(args.output, format=args.format, dry_run=args.dry_run))
        elif args.action == "list":
            dump(store.list(args.evidence_kind))
        elif args.action == "show":
            dump(store.show(args.id))
        elif args.evidence_kind == "paper" and args.action == "verify":
            paper_id = store.verify_paper(
                args.id,
                sha256=args.sha256,
                source_version=args.source_version,
                page_count=args.pages,
                core_operator=args.core_operator,
                primary_logic=args.primary_logic,
                methods=csv(args.methods),
            )
            paper = store.show(paper_id)
            dump({"paper_id": paper_id, "verification": paper["verification_status"]})
        elif args.evidence_kind == "paper" and args.action == "review":
            from .review import add_paper_review
            dump(add_paper_review(
                project, args.id, reviewer=args.reviewer, decision=args.decision, scope=args.scope,
                notes=args.notes, notes_path=args.notes_path,
            ))
        elif args.action == "search":
            dump(store.search(args.query, args.evidence_kind))
        elif args.evidence_kind == "paper":
            print(store.add_paper(args.pdf, args.title, csv(args.authors), args.venue, args.year, args.url, csv(args.tags)))
        else:
            print(store.add_repo(args.name, args.commit, args.url, args.local, csv(args.papers), csv(args.tags), args.notes))
    elif args.root_command == "memory":
        if args.action == "show":
            metadata, body = show_record(project, args.id)
            dump({"metadata": metadata, "body": body})
        elif args.memory_kind == "observation":
            print(add_observation(project, args.title, args.text, csv(args.evidence), args.confidence))
        else:
            print(add_decision(project, args.text, args.why, csv(args.evidence)))
    elif args.root_command == "artifact":
        from .artifact import ArtifactStore
        artifacts = ArtifactStore(project)
        if args.action == "add":
            dump(artifacts.add(
                args.path, title=args.title, artifact_type=args.artifact_type,
                status=args.status, authority=args.authority,
                derived_from=csv(args.derived_from), evidence=csv(args.evidence),
                schema=args.schema, version=args.version,
            ))
        elif args.action == "list":
            dump(artifacts.list(args.status))
        elif args.action == "show":
            dump(artifacts.show(args.id))
        elif args.action == "verify":
            result = artifacts.verify(args.id)
            dump(result)
            return 0 if result["valid"] else 1
        elif args.action == "refresh":
            dump(artifacts.refresh(args.id))
        elif args.action == "supersede":
            dump(artifacts.supersede(args.id, args.by))
        else:
            dump(artifacts.migrate(args.scan, dry_run=args.dry_run))
    elif args.root_command == "knowledge":
        from .knowledge import KnowledgeStore
        knowledge = KnowledgeStore(project)
        if args.action == "rebuild":
            dump(knowledge.rebuild(dry_run=args.dry_run))
        else:
            result = knowledge.check()
            dump(result)
            return 0 if result["valid"] else 1
    elif args.root_command == "scaffold":
        from .scaffold import (
            artifact_scaffold, claim_scaffold, graph_review_scaffold, matrix_entry_scaffold,
            paper_analysis_scaffold, problem_scaffold, synthesis_idea_scaffold,
        )
        if args.scaffold_kind == "paper-analysis":
            print(paper_analysis_scaffold(project, args.paper_id, args.output))
        elif args.scaffold_kind == "matrix-entry":
            print(matrix_entry_scaffold(project, args.paper_id, args.output))
        elif args.scaffold_kind == "synthesis-idea":
            print(synthesis_idea_scaffold(project, args.output))
        elif args.scaffold_kind == "artifact":
            print(artifact_scaffold(args.output, args.path, args.title, args.artifact_type))
        elif args.scaffold_kind == "problem":
            print(problem_scaffold(args.output))
        elif args.scaffold_kind == "claim":
            print(claim_scaffold(args.output))
        elif args.scaffold_kind == "corpus-extraction":
            from .corpus_gap import CorpusStore
            print(CorpusStore(project).scaffold_extraction(args.corpus, args.paper, args.output))
        elif args.scaffold_kind == "paper-adjacency":
            from .scaffold import paper_adjacency_scaffold
            print(paper_adjacency_scaffold(project, args.corpus, args.source, args.target, args.output))
        else:
            print(graph_review_scaffold(project, args.claim, args.output))
    elif args.root_command == "preflight":
        from .scaffold import preflight
        dump(preflight(project, args.kind, args.path))
    elif args.root_command == "migrate":
        if args.migration_kind == "paper-verification":
            from .review import migrate_paper_verification
            dump(migrate_paper_verification(project, dry_run=args.dry_run))
        else:
            from .migration import migrate_corpus_gap_evidence_graph
            dump(migrate_corpus_gap_evidence_graph(
                project, dry_run=args.dry_run, plan_fingerprint=args.plan_fingerprint,
                snapshot_dir=args.snapshot_dir,
            ))
    elif args.root_command == "hypothesis":
        if args.action == "show":
            metadata, body = show_record(project, args.id)
            from .records import hypothesis_provenance_status
            dump({"metadata": metadata, "body": body, "provenance_status": hypothesis_provenance_status(project, metadata)})
        else:
            record_id = add_hypothesis(
                project, args.title, args.statement, csv(args.observations), csv(args.papers),
                args.falsification, ideas=csv(args.ideas), gaps=csv(args.gaps),
            )
            metadata, _ = show_record(project, record_id)
            from .records import hypothesis_provenance_status
            dump({"hypothesis_id": record_id, "provenance_status": hypothesis_provenance_status(project, metadata)})
    elif args.root_command == "daily":
        print(create_daily_log(project))
    elif args.root_command == "doctor":
        checks = run_doctor(args.project, probe_machines=args.probe_machines)
        for check in checks:
            print(f"{check.status:4} {check.name}: {check.detail}")
        failed = any(not check.ok for check in checks)
        warned = any(check.severity == "warning" for check in checks)
        return 1 if failed or (args.strict and warned) else 0
    elif args.root_command == "experiment":
        from .experiments import execute_experiment_command
        return execute_experiment_command(project, args)
    elif args.root_command == "run":
        from .runs import execute_run_command
        return execute_run_command(project, args)
    elif args.root_command == "compute":
        from .compute import execute_compute_command
        return execute_compute_command(args)
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_output()
    try:
        return execute(parser().parse_args(argv))
    except ResearchFlowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
