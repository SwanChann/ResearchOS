# ADR-0006: Verified snapshots and explicit semantic migrations

Status: accepted

## Context

Ordinary local files are readable but not automatically recoverable. The independent Git repository does not cover a separately located ResearchFlow workspace, and changing matrix dimensions or verification semantics can silently reinterpret old records.

## Decision

ResearchFlow provides project-workspace snapshots with per-file SHA-256, external-authority references, safe extraction, dry-run restore, and recoverable confirmed in-place restore. External repositories, Zotero assets, datasets, weights, and large results are not copied by default.

Semantic contract changes are explicit migrations. Matrix axes lock after first use; mappings preserve unmappable old cells and evidence as superseded provenance. Legacy paper verification remains readable and can be upgraded with a previewable, snapshot-backed migration. Human reviews bind to source/content fingerprints and become stale rather than being silently carried forward.

## Consequences

- A snapshot is a verified project record copy, not a complete backup or Git replacement.
- Real-project migrations require separate user authorization even when dry-run fixtures pass.
- File/contract integrity, scoped human review, reproduction, and scientific conclusion remain distinct.
