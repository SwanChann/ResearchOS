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

Project files are authoritative. JSONL registries are append-friendly event/index layers; experiment cards and run records remain authoritative records.

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
- Experiment cards constrain allowed and frozen paths.
- Research lifecycle and compute-job lifecycle are separate.
- Heavy jobs require a single-GPU lock; stale locks are detectable, not silently removed.
- Remote operations and artifact collection support dry-run.
- Remote jobs use an atomic lock directory on the server and append-only state events; this is cooperative coordination, not an operating-system GPU reservation.
- Secrets stay in environment variables, SSH configuration, or credential stores.
- The Zotero adapter accepts loopback `/api` URLs only, implements `GET` only, and never requests or stores a write key.

## Deliberate omissions

V0.3 has no GUI, database, vector store, cloud sync, multi-agent runtime, autonomous endless loop, remote cancellation, or automatic retention cleanup. The real SSH path has only been validated with a CPU-only `TEST / MOCK` fixture; no GPU/heavy validation or scientific claim follows from it. Zotero performs local full-text retrieval; ResearchFlow keeps only the analysis/provenance handoff until measured needs justify more infrastructure.
