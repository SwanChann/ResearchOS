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

The functional core validates records, IDs, transitions, scope, and provenance. Thin service objects provide `ResearchProject` and evidence/experiment access. There is no database, daemon, plugin runtime, scheduler framework, or agent-specific state.

## Data placement

```text
~/.researchflow/config.yaml       global defaults and machine aliases
<research-home>/.projects/<id>/   project research workspace
<repo.local>/                     independent research code Git repository
<remote workspace>/               persistent remote repos/worktrees/runs
```

Project files are authoritative. JSONL registries are append-friendly event/index layers; experiment cards and run records remain authoritative records.

## Safety boundaries

- Formal runs are clean-commit-first by default.
- Experiment cards constrain allowed and frozen paths.
- Research lifecycle and compute-job lifecycle are separate.
- Heavy jobs require a single-GPU lock; stale locks are detectable, not silently removed.
- Remote operations and artifact collection support dry-run.
- Secrets stay in environment variables, SSH configuration, or credential stores.

## Deliberate omissions

V0.1/V0.2 has no GUI, database, vector store, cloud sync, multi-agent runtime, autonomous endless loop, or real GPU invocation. Structured filtering, full-text search, and agent reranking are sufficient until measured retrieval needs justify more infrastructure.

