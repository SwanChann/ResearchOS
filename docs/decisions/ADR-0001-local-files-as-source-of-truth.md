# ADR-0001: Local files are the source of truth

Status: accepted

## Decision

Use ordinary YAML, Markdown, JSON, JSONL, and Git-tracked directories as authoritative storage. Indexes and future databases may be rebuilt from those files.

## Consequences

Records remain readable by people and agents, diff cleanly, and survive tool replacement. Atomic file replacement and file locks are required for counters and mutable records. Cross-machine concurrent writers are outside V0.1.

Local readability does not equal durability. Project snapshots provide verified recovery copies, Git provides version history for paths actually committed to a repository, and a complete backup must separately cover global configuration, Zotero, code repositories, and non-Git assets. Recovery is accepted only after a restore test.
