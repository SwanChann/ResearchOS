from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import jsonschema

from .errors import ValidationError


def schema_dir() -> Path:
    candidates = [
        Path(__file__).resolve().parent.parent / "schemas",
        Path(sys.prefix) / "share" / "researchflow" / "schemas",
    ]
    override = os.environ.get("RESEARCHFLOW_SCHEMA_DIR")
    if override:
        candidates.insert(0, Path(override))
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise ValidationError("ResearchFlow schema files are missing. Reinstall the package or set RESEARCHFLOW_SCHEMA_DIR.")


def validate_record(kind: str, data: dict[str, Any]) -> None:
    path = schema_dir() / f"{kind}.schema.json"
    if not path.exists():
        raise ValidationError(f"Unknown schema: {kind} ({path})")
    import json
    schema = json.loads(path.read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(data)
    except jsonschema.ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "record"
        raise ValidationError(f"Invalid {kind} at {location}: {exc.message}") from exc

