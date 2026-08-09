---
name: literature-query
description: Retrieve project-relevant papers and identify evidence gaps without relying on model memory.
---

# Literature Query

1. Search `evidence/papers/index.jsonl` with structured fields and full text.
2. Open the most relevant `PAPER-*` analyses; inspect the original local PDF for exact claims.
3. If the question is current or about novelty, also perform live search and record URLs/verification date.
4. Return ranked PAPER IDs, claim-level evidence, contradictions, gaps, and whether more live retrieval is required.

Never upgrade `unread` or `skimmed` to `verified` without primary-source inspection. Never infer implementation details from a paper when pinned code is available.
