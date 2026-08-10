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

    commands.add_parser("status", help="show the current research state")

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
        if kind == "repo":
            search_e = actions.add_parser("search")
            search_e.add_argument("query")
    matrix = evidence_actions.add_parser("matrix", help="manage the structured cross-paper literature matrix")
    matrix_actions = matrix.add_subparsers(dest="action", required=True)
    matrix_init = matrix_actions.add_parser("init")
    matrix_init.add_argument("--title", required=True)
    matrix_init.add_argument("--scope", required=True)
    matrix_actions.add_parser("validate")
    matrix_add = matrix_actions.add_parser("add")
    matrix_add.add_argument("entry", type=Path, help="YAML entry containing one verified paper and every matrix axis")
    matrix_synthesize = matrix_actions.add_parser("synthesize")
    matrix_synthesize.add_argument(
        "update", type=Path, help="YAML update containing evidence-linked cross-paper syntheses and ideas"
    )
    matrix_actions.add_parser("render")
    matrix_actions.add_parser("show")
    search = evidence_actions.add_parser("search")
    search.add_argument("query")
    zotero = evidence_actions.add_parser("zotero", help="read from the Zotero-owned literature library")
    zotero_actions = zotero.add_subparsers(dest="action", required=True)
    zotero_configure = zotero_actions.add_parser("configure")
    zotero_configure.add_argument("--base-url", default="http://127.0.0.1:23119/api")
    zotero_configure.add_argument("--library", default="users/0")
    zotero_actions.add_parser("status")
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

    hypothesis = commands.add_parser("hypothesis", help="manage falsifiable hypotheses")
    hypothesis_actions = hypothesis.add_subparsers(dest="action", required=True)
    hyp_new = hypothesis_actions.add_parser("new")
    hyp_new.add_argument("--title", required=True)
    hyp_new.add_argument("--statement", required=True)
    hyp_new.add_argument("--observations")
    hyp_new.add_argument("--papers")
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
            print(f"Created project {args.id}: {workspace}")
        elif args.action == "list":
            print("\n".join(list_projects()) or "No projects.")
        else:
            selected = choose_project(args.id or args.project)
            summary = dict(selected.data)
            summary["workspace"] = str(selected.root)
            summary["startup_files"] = [
                str(selected.root / "AGENTS.md"),
                str(selected.root / "KNOWLEDGE.md"),
                str(selected.root / "memory" / "current-state.md"),
            ]
            summary["explicit_project_command"] = f"rf --project {selected.data['id']} status"
            dump(summary)
        return 0
    project_commands = {"status", "evidence", "memory", "hypothesis", "experiment", "run", "daily"}
    project = choose_project(args.project) if args.root_command in project_commands else None
    if args.root_command == "status":
        dump(project.status())
    elif args.root_command == "evidence":
        store = project.evidence
        if args.evidence_kind == "search":
            dump(store.search(args.query))
        elif args.evidence_kind == "matrix":
            from .literature import LiteratureMatrixStore
            matrix_store = LiteratureMatrixStore(project)
            if args.action == "init":
                print(matrix_store.initialize(args.title, args.scope))
            elif args.action == "validate":
                dump(matrix_store.validate())
            elif args.action == "add":
                print(matrix_store.add_entry_file(args.entry))
            elif args.action == "synthesize":
                dump(matrix_store.synthesize_file(args.update))
            elif args.action == "render":
                print(matrix_store.render())
            else:
                dump(matrix_store.load())
        elif args.evidence_kind == "zotero":
            from .zotero import ZoteroClient, zotero_settings
            if args.action == "configure":
                dump(configure_zotero(args.base_url, args.library))
                return 0
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
        elif args.action == "list":
            dump(store.list(args.evidence_kind))
        elif args.action == "show":
            dump(store.show(args.id))
        elif args.evidence_kind == "paper" and args.action == "verify":
            print(store.verify_paper(
                args.id,
                sha256=args.sha256,
                source_version=args.source_version,
                page_count=args.pages,
                core_operator=args.core_operator,
                primary_logic=args.primary_logic,
                methods=csv(args.methods),
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
    elif args.root_command == "hypothesis":
        if args.action == "show":
            metadata, body = show_record(project, args.id)
            dump({"metadata": metadata, "body": body})
        else:
            print(add_hypothesis(project, args.title, args.statement, csv(args.observations), csv(args.papers), args.falsification))
    elif args.root_command == "daily":
        print(create_daily_log(project))
    elif args.root_command == "doctor":
        checks = run_doctor(args.project, probe_machines=args.probe_machines)
        for check in checks:
            print(f"{'OK' if check.ok else 'FAIL':4} {check.name}: {check.detail}")
        return 0 if all(check.ok for check in checks) else 1
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
