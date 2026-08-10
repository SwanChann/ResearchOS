# Schemas

Machine-readable JSON Schemas live in `schemas/` and are packaged as installation data. Records are validated before write and again when opened where practical.

- `project`: project identity plus research-repository reference.
- `paper`: literature metadata and verification state; a Zotero-linked source may contain database/library/item/version provenance while `local_pdf` remains null.
- `repository_evidence`: URL/local path plus mandatory commit pin.
- `observation`, `hypothesis`, `decision`: epistemically distinct Markdown records with YAML frontmatter.
- `experiment`: lifecycle, scope, metrics, budgets, approvals, and execution command.
- `run`: one execution and its Git/config/environment/hardware/artifact provenance.

References are checked before memory records are created. A broken reference is rejected with the missing ID and project rather than persisted as a dangling scientific claim.
