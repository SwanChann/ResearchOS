---
name: paper-deep-read
description: Turn one primary paper PDF into a page-cited, claim-strength-calibrated ResearchFlow analysis with bounded idea seeds.
---

# Paper Deep Read

## Required inputs

- One linked `PAPER-*` record and its Zotero-owned primary PDF, or one legacy ResearchFlow-owned PDF.
- The exact file SHA-256, source version, and PDF page count.
- The current project question, if relevance is assessed.

## Procedure

1. Read the entire primary document, including appendices and limitations. Render important architecture, result, and failure-analysis pages; text extraction alone is insufficient for layout-sensitive evidence.
2. Record citations using viewer PDF pages (`p. N` or `pp. N-M`) and name the table, figure, or section when available. Never silently substitute printed manuscript numbering.
3. Classify each claim:
   - `S1`: direct quantitative result transcribed from a named experiment, table, or figure;
   - `S2`: direct descriptive method, procedure, or limitation;
   - `S3`: author interpretation or generalization from the evidence;
   - `S4`: analyst inference or project-specific implication.
4. State the scope of every important claim. Paper-source verification proves correspondence to the document, not independent reproduction or universal validity.
5. Keep critique separate from paper claims. Look for comparator scope, sample size, uncertainty, hidden system dependencies, deployment boundaries, negative results, and failure cases.
6. Write each idea seed with trigger, proposed mechanism, supporting claim IDs/pages, counterevidence or risk, novelty status, smallest falsification test, and promotion rule. Mark novelty `unchecked` until a separate current literature search.
7. Remove all unread placeholders, then run `rf evidence paper verify` with the document fingerprint and method labels. Do not mark `verified` if page citations or primary-source inspection are missing.

## Output contract

The analysis must retain these level-two headings: `Source Snapshot`, `Claim Strength Scale`, `Verified Claims`, `Critical Assessment`, and `Idea Seeds`. It must contain at least one `Cnn` claim ID, one PDF page citation, and one `IDEA-nn` seed.

## Write-back rules

- Zotero remains authoritative for bibliography, PDFs, collections, notes, annotations, and citation formatting. Store only the source reference/fingerprint and ResearchFlow analysis.
- An idea seed is not a finding or approved experiment. Promote it to `HYP-*` only after the research question and falsification rule are reviewed.
- Never write a paper-reported result as a project result, and never treat `verified` as `reproduced`.
