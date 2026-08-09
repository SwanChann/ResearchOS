# ADR-0001: Local files are the source of truth

Status: accepted

## Decision

Use ordinary YAML, Markdown, JSON, JSONL, and Git-tracked directories as authoritative storage. Indexes and future databases may be rebuilt from those files.

## Consequences

Records remain readable by people and agents, diff cleanly, and survive tool replacement. Atomic file replacement and file locks are required for counters and mutable records. Cross-machine concurrent writers are outside V0.1.

