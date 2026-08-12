---
name: literature-query
description: Retrieve project-relevant papers and identify evidence gaps without relying on model memory.
---

# Literature Query

1. Search `evidence/papers/index.jsonl` for existing ResearchFlow analyses.
2. If Zotero is configured, use `rf evidence zotero search` for Zotero-owned metadata/full-text retrieval and `show` for the current attachment, note, and annotation context.
3. Open the most relevant `PAPER-*` analyses. Inspect the Zotero-owned primary PDF before verifying exact claims; do not copy the PDF into ResearchFlow.
4. If the question is current or about novelty, also perform live search and record URLs/verification date.
5. Return ranked PAPER IDs or Zotero item keys, claim-level evidence, contradictions, gaps, and whether linking or more live retrieval is required.
6. For a formal cross-paper comparison, inspect `rf evidence matrix templates list`; use generic, a named domain template, or a confirmed project axes YAML. Generate entries with `rf scaffold matrix-entry`, run `rf preflight matrix-entry`, and write through `rf evidence matrix add`.
7. Do not edit embedded axes after the first paper. Prepare an explicit `matrix migrate ... --dry-run` mapping and request authorization before migrating a real project.

Never upgrade `unread` or `skimmed` to source-verified without primary-source inspection. A scaffold or generic analysis report is an agent-generated draft, not a formal ResearchFlow record until it passes the CLI contract. Never infer implementation details from a paper when pinned code is available.
