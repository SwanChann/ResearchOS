# Schemas

Machine-readable JSON Schemas live in `schemas/` and are packaged as installation data. Records are validated before write and again when opened where practical.

- `project`: project identity plus research-repository reference.
- `paper`: literature metadata and verification state; a Zotero-linked source may contain database/library/item/version provenance while `local_pdf` remains null. A completed deep read may also store the inspected document fingerprint/version/page count and searchable method labels, but never a second PDF.
- `literature_matrix`: one project-level structured cross-paper comparison. It pins each included verified paper's source fingerprint, requires an explicit cell for every configured axis, and stores page/claim references for supported cells. YAML frontmatter is authoritative; Markdown tables are generated.
- `repository_evidence`: URL/local path plus mandatory commit pin.
- `observation`, `hypothesis`, `decision`: epistemically distinct Markdown records with YAML frontmatter.
- `experiment`: lifecycle, scope, metrics, budgets, approvals, and execution command.
- `run`: one execution and its Git/config/environment/hardware/artifact provenance.

References are checked before memory records are created. A broken reference is rejected with the missing ID and project rather than persisted as a dangling scientific claim.
