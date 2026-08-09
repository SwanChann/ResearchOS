from __future__ import annotations

import argparse

from .errors import ResearchFlowError


def add_experiment_parser(commands) -> None:
    command = commands.add_parser("experiment", help="design and execute bounded experiments")
    command.add_subparsers(dest="action", required=True)


def execute_experiment_command(project, args: argparse.Namespace) -> int:
    raise ResearchFlowError("Experiment commands are unavailable until the Git experiment layer is installed.")

