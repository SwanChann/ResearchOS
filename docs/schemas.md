# Schemas

Machine-readable JSON Schemas live in `schemas/` and are packaged as installation data. Records are validated before write and again when opened where practical.

- `project`: project identity plus research-repository reference.
- `paper`: literature metadata, document fingerprint, structured verification layers, and fingerprint-bound human reviews. Legacy `status: verified` remains readable but is not interpreted as reproduction or scientific establishment.
- `literature_matrix`: one project-level structured cross-paper comparison. Schema v1 remains readable; schema v2 adds axes version/source/lock/migration provenance and optional fingerprint-bound reviews. Unmappable migrated cells remain under `superseded_cells` with evidence intact.
- `artifact_registry`: `ARTIFACT-*` identity, project-relative path, SHA-256, status, authority, lineage/evidence, supersession chain, and timestamps. Hash validity is not scientific validity.
- `repository_evidence`: URL/local path plus mandatory commit pin.
- `observation`, `hypothesis`, `decision`: epistemically distinct Markdown records with YAML frontmatter. Hypothesis remains backward compatible while optionally storing `XIDEA-*` provenance, recursive PAPER/claim refs, novelty warnings, and staleness fingerprints.
- `experiment`: lifecycle, scope, metrics, budgets, approvals, and execution command.
- `run`: one execution and its Git/config/environment/hardware/artifact provenance.
- `problem` / `problem_request`: stable research scope and the Agent-editable import request. A Problem is not evidence that a Gap exists.
- `claim` / `claim_request`: a bounded draft Claim with datasets, platforms, seeds, conditions, qualifiers, experimental-result Findings, and exact Run/Artifact/JSON-Pointer metric evidence.
- `evidence_graph`: typed, fingerprint-bound relation ledger. Only this ledger is authoritative; the JSON index is derived.
- `evidence_graph_audit`: immutable L1 result plus explicit pending/pass/fail/unavailable/stale L2 and fidelity states. Only `pass` counts as pass.
- `corpus_scope` / `corpus`: a declared review scope plus frozen matrix and verified-paper source fingerprints.
- `corpus_extraction_request` / `corpus_extraction`: locator-bound normalized tuples, immutable content fingerprint, and append-only human review history.
- `motif_rules` / `gap` / `corpus_gap_run`: deterministic candidate derivation, explicitly heuristic scores, human approval, counterevidence, and TEST/MOCK isolation.
- `paper_adjacency_request` / `paper_adjacency`: evidence-bound PAPER-to-PAPER candidate import, deterministic build provenance, Paper-analysis fingerprints, human review, and staleness.
- `corpus_extraction_v2_request` / `corpus_extraction_v2`: richer source-bounded tuples plus nine explicit coverage dispositions; V1 remains supported.
- `concept_request` / `concept_vocabulary`: typed aliases and broader/related concepts behind fingerprint-bound human review.
- `adjacency_benchmark`: human-reviewed positive/negative cases for benchmark-scoped generator evaluation.
- `evidence_graph_review_request`: provider-neutral, input-fingerprint-bound L2/L3 import.
- `evidence_graph_migration`: reviewed exact-reference migration, verified snapshot path, and rollback command.
- `metric_alias_map`: versioned exact alias mapping for metric paths; fuzzy matching remains forbidden.

References are checked before memory records are created. A broken reference is rejected with the missing ID and project rather than persisted as a dangling scientific claim.

`CLAIM-*` never accepts an unscoped `true` or `verified` state. Initial import is `draft`, semantic review starts `pending`, reproduction starts `not_checked`, and `scientific_establishment` remains `not_established`. Metric checks use exact canonical IDs and JSON Pointers; fuzzy key matching is not part of the contract.

Unknown fields are rejected by formal schemas rather than silently discarded. Axes and paper verification upgrades are explicit migrations with `--dry-run`; non-dry-run migration creates a workspace snapshot and is idempotent on replay.

Axes YAML uses `schema_version: 1`, `status: draft|confirmed`, a stable `version`, and axes with stable lowercase `id`, `label`, `group`, and `description`. A matrix migration YAML has this shape:

```yaml
schema_version: 1
matrix_id: LITMATRIX-0001
from_axes_version: project-v1
target:
  template: generic        # or axes_file: relative/path.yaml
mapping:
  old_method: method_architecture
```

Run `rf evidence matrix migrate migration.yaml --dry-run` first. A real-project write still requires explicit authorization; a successful fixture preview is not authorization.
