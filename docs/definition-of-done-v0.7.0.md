# ResearchFlow V0.7.0 Definition of Done

## Delivered boundary

- `PADJ-*` is a schema-validated, project-local PAPER-to-PAPER authority record.
- Deterministic generation reads only current, human-accepted Corpus extractions and makes no model or network call.
- Manual, Agent, and tool proposals use the same preflight/import contract and must cite both Papers with claims and locators.
- Human acceptance is fingerprint-bound; changed Papers, Corpus sources, extraction reviews, tuples, edge content, or reviews fail closed.
- Accepted current edges support neighbor/explanation queries, JSON/DOT export, explicit EvidenceGraph promotion, and adjacency-aware Gap motifs.
- Absence-based Gap candidates are invalidated when the accepted adjacency set changes.
- New-project initialization, status, doctor, record resolution, packaging, documentation, and CLI help include the module.

## Explicit non-claims

- Structural adjacency does not prove semantic relatedness, novelty, correctness, or a research Gap.
- V0.7.0 does not include a built-in PDF parser, embedding model, LLM provider, autonomous reviewer, web discovery service, or vector database.
- TEST/MOCK fixtures verify software behavior only.
- No real ResearchFlow project is migrated or modified by this release implementation.

## Release gate

The local implementation is releasable after the full test suite, Python compilation, JSON Schema parsing, wheel build, installed CLI/schema smoke test, and whitespace check pass. A local Git checkpoint and any real-project adoption require separate authorization.
