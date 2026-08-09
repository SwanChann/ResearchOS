from __future__ import annotations

import argparse

from .errors import ResearchFlowError


def add_compute_parser(commands) -> None:
    command = commands.add_parser("compute", help="manage local and SSH compute targets")
    command.add_subparsers(dest="action", required=True)


def execute_compute_command(args: argparse.Namespace) -> int:
    raise ResearchFlowError("Compute commands are unavailable until the remote compute abstraction is installed.")

