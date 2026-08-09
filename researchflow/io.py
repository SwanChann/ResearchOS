from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Iterator

import yaml

from .errors import ResearchFlowError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ResearchFlowError(f"Required YAML file does not exist: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ResearchFlowError(f"Cannot read YAML {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ResearchFlowError(f"Expected a YAML mapping in {path}")
    return data


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    atomic_text(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ResearchFlowError(f"Invalid JSONL at {path}:{number}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ResearchFlowError(f"Expected JSON object at {path}:{number}")
        records.append(value)
    return records


@contextmanager
def exclusive_lock(path: Path, timeout: float = 5.0) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = monotonic() + timeout
    while True:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"pid={os.getpid()}\n".encode())
            os.close(descriptor)
            break
        except FileExistsError:
            if monotonic() >= deadline:
                raise ResearchFlowError(f"Timed out waiting for lock: {path}")
            sleep(0.05)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def markdown_record(metadata: dict[str, Any], body: str) -> str:
    frontmatter = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).rstrip()
    return f"---\n{frontmatter}\n---\n\n{body.strip()}\n"


def read_markdown_record(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ResearchFlowError(f"Markdown record lacks YAML frontmatter: {path}")
    try:
        frontmatter, body = text[4:].split("\n---\n", 1)
        metadata = yaml.safe_load(frontmatter) or {}
    except (ValueError, yaml.YAMLError) as exc:
        raise ResearchFlowError(f"Invalid Markdown frontmatter in {path}: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ResearchFlowError(f"Expected frontmatter mapping in {path}")
    return metadata, body.lstrip()

