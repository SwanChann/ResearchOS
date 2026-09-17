# Definition of Done: ResearchFlow 0.8.2

ResearchFlow 0.8.2 is complete when all of the following are true:

- Knowledge, Corpus, EvidenceGraph, and PaperAdjacency status paths reuse operation-local inputs without changing authoritative records.
- Existing accepted semantic edges remain current against the generator version recorded on each edge when their evidence inputs are unchanged.
- Exact comparison-baseline failure evidence and guarded broader-family boundary cases produce review candidates without treating comparison as extension or Method-family overlap as same-problem evidence.
- Benchmark evaluation reports false-negative diagnoses that distinguish missing structured evidence from a missing generator rule.
- The full TEST/MOCK suite, `compileall`, CLI loading, and `git diff --check` pass.
- Read-only `embodied-nav` validation reports benchmark-scoped metrics and does not write candidates, reviews, graph edges, research records, or scientific claims.
- A local Git checkpoint exists. Remote publication is a separate durability action and requires a configured destination.
