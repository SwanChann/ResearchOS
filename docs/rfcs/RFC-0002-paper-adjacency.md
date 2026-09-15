# RFC-0002: PaperAdjacency

- Status: implemented locally; real-project adoption pending
- Target version: ResearchFlow 0.7.0
- Scope: evidence-bound PAPER-to-PAPER relationships and adjacency-aware Gap detection

## 1. Problem

ResearchFlow 0.6.0 can verify individual deep reads, compare Papers in a Matrix, freeze a Corpus, and extract Paper-reported tuples. It cannot represent or query a first-class PAPER-to-PAPER relationship. Free-text roles such as “direct neighbor” are not typed, fingerprint-bound, reviewable, or consumable by CorpusGap.

## 2. Decision

Add a project authority ledger at `.research/paper-adjacency/edges.yaml`. A `PADJ-*` edge is a multi-dimensional, evidence-bound relationship between two verified Papers in one frozen Corpus. Similarity is not authority: deterministic or model-assisted generation creates a candidate; only a current `human:*` acceptance makes it usable by Gap detection or promotable to EvidenceGraph.

Supported relations:

- symmetric: `same_problem`, `same_method_family`, `shares_assumption`, `same_evaluation`;
- directed: `extends_method`, `replaces_component`, `relaxes_assumption`, `contradicts_result`, `addresses_limitation`, `exposes_failure`, `counterevidence`, `boundary_case`.

Every edge stores both Paper analysis fingerprints, the Corpus, evidence Claim IDs and locators, optional accepted extraction tuple IDs, dimensions, an explicit rationale, heuristic scores, generator provenance, and append-preserving review history.

## 3. Deterministic structural generation

`adjacency build` reads only current human-accepted Corpus extractions. Version `structural-v1` derives:

| shared/linked structure | candidate relation |
|---|---|
| Task key | `same_problem` |
| Method key | `same_method_family` |
| Assumption key | `shares_assumption` |
| Dataset or Metric key | `same_evaluation` |
| a Paper reports `Method fails_under FailureCondition`, another contains that Method | `exposes_failure` |

No title similarity, fuzzy key matching, or model judgment is treated as a deterministic edge. Advanced relations enter through the scaffold/preflight/import contract and remain candidates until human acceptance.

## 4. CLI

```text
rf evidence adjacency build --corpus CORPUS-0001 [--dry-run]
rf evidence adjacency add REQUEST.yaml [--dry-run]
rf evidence adjacency list [--status ...] [--corpus ...]
rf evidence adjacency show PADJ-000001
rf evidence adjacency neighbors PAPER-0001 [--status accepted] [--top-k 10]
rf evidence adjacency explain PAPER-0001 PAPER-0002
rf evidence adjacency review PADJ-000001 --decision accepted --reviewer human:NAME --rationale-file FILE
rf evidence adjacency check
rf evidence adjacency export --output FILE --format json|dot [--dry-run]
rf evidence adjacency promote PADJ-000001 [--dry-run]
rf scaffold paper-adjacency --corpus ID --from PAPER-ID --to PAPER-ID --output FILE
rf preflight paper-adjacency FILE
```

`promote` is explicit. It copies one current accepted relationship into EvidenceGraph and uses the PADJ record as mandatory provenance. It does not silently promote every candidate.

## 5. Gap integration

Motif rules may use `adjacency_match` and `adjacency_absence_match`. Three adjacency-aware motifs are available:

- `adjacency_missing_relation`;
- `adjacency_contradiction`;
- `adjacency_boundary_gap`.

Example: an accepted `exposes_failure` edge plus the absence of an accepted `addresses_limitation` edge can create a candidate Gap. Adding accepted counterevidence changes the adjacency input fingerprint, makes the older candidate stale, and may close the candidate on the next deterministic scan.

Only accepted, current PADJ records participate. A Gap remains heuristic and still requires separate human approval.

## 6. Staleness and safety

- A PDF/source change invalidates the Corpus and related adjacency.
- A Paper deep-read/Claim change invalidates related adjacency even when the PDF is unchanged.
- Accepted adjacency review binds to the exact adjacency fingerprint.
- Rejected and stale edges are excluded from neighbor results used by default and from Gap detection.
- Dry-run does not allocate IDs or write authority files.
- The ledger uses atomic replacement and a project lock.
- TEST/MOCK fixtures prove software behavior only.

## 7. Provider boundary

V0.7.0 has no built-in embedding or LLM provider. A human, Agent, or tool may produce a schema-valid request using `generator.kind=human|agent_import|tool_import`; ResearchFlow validates evidence and provenance but does not regard the provider score as scientific evidence. Provider selection, paid calls, external retrieval, and autonomous extraction require a separate decision.

## 8. Acceptance

- deterministic build is idempotent for the same Corpus/extraction fingerprints;
- every edge explains the relation using Claim IDs and source locators;
- only `human:*` can accept an edge;
- a changed Paper analysis makes the edge and promoted EvidenceGraph edge stale;
- neighbors return only current accepted edges by default;
- an accepted failure relation can trigger an adjacency-aware Gap candidate;
- an accepted addressing relation closes that candidate and stales the older Gap;
- focused and full tests, compileall, CLI help traversal, and `git diff --check` pass before release checkpoint.

## 9. Remaining human decision

The local deterministic and provider-neutral contracts do not require a provider choice. Before automatic semantic recall is implemented, the user must choose whether V0.7.x should use a local embedding model, an external API, or both through adapters. Before real-project validation, the user must separately authorize which project may receive PADJ records and human reviews.
