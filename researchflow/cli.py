from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from .config import init_config, load_config, save_config
from .daily import create_daily_log
from .doctor import run_doctor
from .errors import ResearchFlowError
from .project import ResearchProject, add_project, list_projects, project_path
from .records import add_decision, add_hypothesis, add_observation, show_record


def csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


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
        if kind == "repo":
            search_e = actions.add_parser("search")
            search_e.add_argument("query")
    search = evidence_actions.add_parser("search")
    search.add_argument("query")

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
    commands.add_parser("doctor", help="check configuration and project integrity")
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
            dump(choose_project(args.id or args.project).data)
        return 0
    project_commands = {"status", "evidence", "memory", "hypothesis", "experiment", "run", "daily"}
    project = choose_project(args.project) if args.root_command in project_commands else None
    if args.root_command == "status":
        dump(project.status())
    elif args.root_command == "evidence":
        store = project.evidence
        if args.evidence_kind == "search":
            dump(store.search(args.query))
        elif args.action == "list":
            dump(store.list(args.evidence_kind))
        elif args.action == "show":
            dump(store.show(args.id))
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
        checks = run_doctor(args.project)
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
    try:
        return execute(parser().parse_args(argv))
    except ResearchFlowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
