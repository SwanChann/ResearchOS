# Workflow

## Research lifecycle

```text
Question -> Evidence -> Observation -> Hypothesis -> Experiment Card
         -> approval/scope preflight -> Run -> raw results -> Observation
         -> human/policy Decision
```

Experiment state transitions are validated; `DRAFT -> FULL_RUN` is rejected.

```text
DRAFT -> EVIDENCE_READY -> HYPOTHESIS_APPROVED -> IMPLEMENTED
      -> SMOKE_TEST -> PILOT -> PILOT_PASS -> FULL_APPROVED
      -> FULL_RUN -> ANALYZED -> DECIDED
      -> ACCEPTED | REJECTED | INCONCLUSIVE | FOLLOW_UP
```

Failure branches are persistent: `SMOKE_TEST -> FAILED_SMOKE` and `PILOT -> ANALYZE_FAILURE`. Failed commits and run records are retained as evidence.

## Compute-job lifecycle

Research status is separate from execution status:

```text
QUEUED -> PREFLIGHT -> GPU_WAIT -> RUNNING
       -> SUCCEEDED | FAILED | CANCELLED
       -> COLLECTED -> REGISTERED
```

The local runner performs this lifecycle synchronously and registers every attempted run. The SSH runner starts in the background, persists its current state in `job.json`, and appends transitions to `events.jsonl`; `compute collect` registers a terminal job locally. A successful process without a valid JSON-object `metrics.json` is recorded as failed because result collection is incomplete.

## Run provenance

Every successful run directory contains `run.yaml`, `run.log`, `metrics.json`, and `environment.json`. Remote runs additionally retain `job.json`, `events.jsonl`, the submitted experiment card, and supervisor output when present. The run record links its experiment, level, command, exact commit, dirty flag/diff hash, configuration hash, environment, host/GPU request, metrics, artifacts, timestamps, and exit code. Fixture runs carry `test_only: true` and visible `TEST / MOCK` labels.

Remote collection is intentionally narrow: only small text/JSON/YAML provenance files are copied, with a 10 MiB limit per file. Datasets, checkpoints, videos, and remote worktrees remain on the server.

## Git-first boundary

The card captures a baseline commit. `rf experiment worktree` creates a detached worktree from that commit. Before execution, `preflight` checks the card, state, hypothesis, commit, clean/dirty state, config, modified paths, metrics, guardrails, stop conditions, command, tests, GPU count, and full approval. `--allow-dirty` is exceptional and provenance must preserve the diff hash.
