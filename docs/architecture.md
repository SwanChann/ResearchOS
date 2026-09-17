# Architecture

## Boundary

ResearchFlow is a local control plane. A project workspace stores research state and evidence indexes; the configured research repository remains the data plane and owns executable source code. Remote machines are persistent compute targets, not disposable copies.

## Layers

```text
CLI / small Python API
        |
workflow rules and validation
        |
filesystem adapters + Git/SSH subprocess boundaries
        |
YAML, Markdown, JSON, JSONL, ordinary directories
```

The functional core validates records, IDs, transitions, scope, and provenance. Thin service objects provide `ResearchProject` and evidence/experiment access. The Zotero adapter is a read-only loopback boundary, not a second literature store. There is no database, daemon, plugin runtime, scheduler framework, or agent-specific state.

## Data placement

```text
~/.researchflow/config.yaml       global defaults and machine aliases
<research-home>/.projects/<id>/   project research workspace
<repo.local>/                     independent research code Git repository
<remote workspace>/               persistent remote repos/worktrees/runs
```

Project files are authoritative. JSONL registries are append-friendly event/index layers; experiment cards and run records remain authoritative records. `.research/artifacts.yaml` is the atomic Artifact registry. `.research/paper-adjacency/edges.yaml` is the evidence-bound PAPER-to-PAPER authority; `.research/paper-adjacency/concepts.yaml` is its separately human-reviewed normalization vocabulary. Comparison packets and benchmark reports are computed views, not authority ledgers. `.research/evidence-graph/edges.yaml` is the broader typed relationship authority while its `index.json` is deterministically rebuildable. `KNOWLEDGE.md` contains a delimited generated navigation view plus user-owned prose.

Snapshots are portable ZIP containers with a hashed manifest and safe manual extraction. Creation uses a temporary target followed by atomic replacement. Restore defaults to a new directory; in-place restore creates a recoverable sibling copy before replacement. Repositories, Zotero PDFs, datasets, weights, and other external authorities are referenced in the manifest but excluded by default.

## Core repository

```text
researchflow/
  researchflow/       compact Python package (CLI + functional modules)
  schemas/            JSON record contracts
  templates/          editable human-readable starting points
  skills/             agent-agnostic workflow instructions
  examples/
    toy-research/      deterministic TEST/MOCK E2E fixture
    embodied-nav/      domain profile examples, no claimed results
  tests/               unit, safety, CLI, and E2E tests
  docs/                contracts, workflow, ADRs, development
```

The Python package is deliberately flat. Modules correspond to stable nouns (`project`, `evidence`, `experiments`, `runs`, `compute`) or small infrastructure boundaries (`io`, `schema`, `gitops`).

## Safety boundaries

- Formal runs are clean-commit-first by default.
- Local Git commands trust only the explicitly selected repository for that invocation; ResearchFlow does not require a global `safe.directory` exception on shared Windows installations.
- Experiment cards constrain allowed and frozen paths.
- Research lifecycle and compute-job lifecycle are separate.
- Heavy jobs require a single-GPU lock; stale locks are detectable, not silently removed.
- Remote operations and artifact collection support dry-run.
- Ordinary integrity checks are local-only; live machine probes require an explicit flag.
- Remote jobs use an atomic lock directory on the server and append-only state events; this is cooperative coordination, not an operating-system GPU reservation.
- Secrets stay in environment variables, SSH configuration, or credential stores.
- The Zotero adapter accepts loopback `/api` URLs only, implements `GET` only, and never requests or stores a write key. Its doctor classifies configuration, transport, identity, item/library, and local attachment-path failures without downloading attachments.
- Schema/contract validation, source fingerprinting, human review, reproduction, and scientific establishment are separate layers. Reviews are bound to content fingerprints and become stale after relevant content changes.
- Matrix axes are embedded and versioned. They lock on first insertion; changes require a mapping file, dry-run, automatic snapshot, preserved superseded cells, and migration provenance.
- EvidenceGraph endpoints resolve back to ordinary authoritative records and bind edges to both endpoint fingerprints. Changed endpoints require a new edge that explicitly supersedes the old version. Structural/metric checks, semantic review, reproduction, and scientific establishment remain distinct.

## Deliberate omissions

V0.8.1 has no built-in PDF parser, embedding/LLM provider, autonomous semantic reviewer, automatic graph repair loop, GUI, database, vector store, cloud sync, multi-agent runtime, autonomous endless loop, remote cancellation, or automatic retention cleanup. Semantic adjacency is deterministic normalization and tuple matching, not embedding similarity or semantic truth. CorpusGap outputs remain heuristic candidates behind human gates. Snapshots are project-workspace copies, not a scheduler or complete machine backup. No TEST/MOCK result establishes GPU behavior or a scientific claim.
