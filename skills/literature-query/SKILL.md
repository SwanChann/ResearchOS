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

Never upgrade `unread` or `skimmed` to `verified` without primary-source inspection. Never infer implementation details from a paper when pinned code is available.
