from __future__ import annotations

import argparse

from .errors import ResearchFlowError


def add_run_parser(commands) -> None:
    command = commands.add_parser("run", help="inspect registered runs")
    command.add_subparsers(dest="action", required=True)


def execute_run_command(project, args: argparse.Namespace) -> int:
    raise ResearchFlowError("Run commands are unavailable until the local run layer is installed.")

