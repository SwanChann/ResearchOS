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

References are checked before memory records are created. A broken reference is rejected with the missing ID and project rather than persisted as a dangling scientific claim.

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
