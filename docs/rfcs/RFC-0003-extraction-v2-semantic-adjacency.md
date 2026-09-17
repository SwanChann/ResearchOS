# RFC-0003: Extraction V2 and semantic PaperAdjacency

Status: implemented locally in ResearchFlow 0.8.1; real-project adoption requires separate authorization.

## Problem

V1 extraction accepts sparse tuples without recording which literature dimensions were checked. Exact-key structural adjacency therefore cannot distinguish “paper did not report this” from “extractor omitted this,” and aliases or method families fragment otherwise comparable evidence.

## Decision

1. Extraction V2 adds source-bounded assertions and nine required coverage dispositions: problem, method/components, training, evaluation, results, assumptions, limitations, failure conditions, and prior-work delta.
2. A project vocabulary stores typed canonical keys, aliases, broader concepts, and related concepts. Only a `human:*` review can accept normalization. Vocabulary edits change a fingerprint and stale dependent semantic edges.
3. Semantic generation is deterministic over accepted extraction tuples and accepted concepts. It emits candidates for normalized shared dimensions and explicit `extends`, `replaces`, `addresses`, `contradicts`, and `fails_under` tuples. Method-family matching uses adoption/proposal roles rather than comparison endpoints. Failure propagation requires the same canonical method or a broader-family match plus shared task, assumption, or failure context. It never accepts an edge.
4. A comparison packet ranks paper pairs using exact and token-overlap recall signals and includes source tuple evidence. It is a reading queue, not an adjacency ledger.
5. Evaluation consumes a fingerprinted, `human:*`-reviewed benchmark and reports TP/FP/FN/TN, precision, recall, and F1 within that benchmark only. A negative benchmark label that conflicts with a deterministic accepted-ontology relation fails closed before metrics are reported.

## Authority and safety

- Paper analysis and accepted extraction remain the evidence source.
- Concept records are analyst ontology, not paper claims.
- `PADJ-*` acceptance remains human-only and fingerprint-bound.
- Dry-run and packet/evaluate operations do not modify the project.
- V1 remains readable; no automatic migration is performed.
- TEST/MOCK validation proves software behavior only.

## CLI

```text
rf scaffold corpus-extraction-v2 --corpus ID --paper ID --output FILE
rf preflight corpus-extraction-v2 FILE
rf evidence adjacency concept-add FILE [--dry-run]
rf evidence adjacency concept-list|concept-show|concept-resolve|concept-check ...
rf evidence adjacency concept-review ID --decision ... --reviewer human:NAME --rationale-file FILE
rf evidence adjacency build --corpus ID --mode semantic --details --dry-run
rf evidence adjacency packet --corpus ID --top-k 25
rf evidence adjacency evaluate --corpus ID --benchmark FILE --mode semantic
```

## Compatibility and migration

V1 and V2 extraction schemas coexist. Existing Corpora require no write or migration. Adoption is paper-by-paper: scaffold/import/review V2 extractions and optionally add/review concepts. A Corpus can technically contain mixed schema versions, but comparisons must report those versions; a scientific refresh should define and enforce its own completeness policy.

## Acceptance tests

- V1 extraction and structural adjacency remain backward compatible.
- V2 rejects a `covered` category without a matching tuple and rejects a conflicting `not_reported` disposition.
- Concept acceptance is human-only; duplicates, missing accepted parents, and hierarchy cycles fail closed.
- Semantic candidates are deterministic, evidence-bound, and stale when inputs change.
- Packet creation writes no authoritative edge.
- Benchmark evaluation reproduces known TEST/MOCK precision, recall, and F1.
- CLI help, JSON Schemas, package install, and the full regression suite pass.
