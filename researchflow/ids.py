from __future__ import annotations

import re
from pathlib import Path

from .errors import ResearchFlowError
from .io import exclusive_lock, read_yaml, write_yaml

ID_WIDTHS = {
    "PAPER": 4,
    "REPO": 4,
    "OBS": 4,
    "HYP": 4,
    "EXP": 4,
    "RUN": 6,
    "DEC": 4,
}


def allocate_id(home: Path, kind: str) -> str:
    kind = kind.upper()
    if kind not in ID_WIDTHS:
        raise ResearchFlowError(f"Unknown ID kind {kind}. Expected one of: {', '.join(ID_WIDTHS)}")
    counter_path = home / ".id-counters.yaml"
    with exclusive_lock(home / ".locks" / "id-allocation.lock"):
        counters = read_yaml(counter_path) if counter_path.exists() else {}
        value = int(counters.get(kind, 0)) + 1
        counters[kind] = value
        write_yaml(counter_path, counters)
    return f"{kind}-{value:0{ID_WIDTHS[kind]}d}"


def validate_id(value: str, kind: str | None = None) -> bool:
    match = re.fullmatch(r"([A-Z]+)-(\d+)", value)
    if not match or match.group(1) not in ID_WIDTHS:
        return False
    prefix, digits = match.groups()
    return (kind is None or prefix == kind.upper()) and len(digits) == ID_WIDTHS[prefix]

