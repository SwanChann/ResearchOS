# Workflow

## Research lifecycle

```text
Question -> Evidence -> Observation -> Hypothesis -> Experiment Card
         -> approval/scope preflight -> Run -> raw results -> Observation -> Claim
         -> human/policy Decision
```

A matrix `XIDEA-*` may also feed a Hypothesis directly. ResearchFlow stores the Idea, its matrix fingerprint, and recursive PAPER/claim references; a literature-only Hypothesis is explicitly marked as lacking local empirical support. Matrix or Idea changes make that provenance stale.

## Contract-first literature and artifact workflow

```text
link/add Paper -> generated analysis shell -> preflight -> source/fingerprint verify
               -> optional scoped human review (fingerprint-bound)
confirmed matrix axes -> first Paper locks version -> entries -> synthesis/Idea
                     -> optional review -> explicit migration when axes change
ordinary project file -> Artifact draft registration -> hash/reference verify
formal registries -> KNOWLEDGE generated region -> check/rebuild
```

Use CLI scaffolds before formal writes. A scaffold may intentionally fail preflight until claims/evidence are filled; it is an agent-generated draft, never a formal ResearchFlow record merely because it is Markdown or YAML. All formal mutable files are atomically replaced. Migrations support dry-run and create a snapshot before a real rewrite.

RFC-0001 adds two gated paths:

```text
Problem record
verified Matrix -> frozen Corpus -> locator-bound extraction -> human acceptance
                -> deterministic candidate Gap -> human approval -> Hypothesis
HYP -[tested_by]-> EXP -[produces]-> experimental_result OBS -[supports]-> CLAIM
                               exact RUN + Artifact hash + JSON Pointer value
```

The graph index is rebuilt from authoritative records and `edges.yaml`. A complete L1 path still leaves semantic review pending. L2/L3 enters through an explicit fingerprint-bound review file. Corpus extraction and Gap promotion each have independent human gates; no motif or model output becomes a Hypothesis automatically.

## Recovery workflow

Create a snapshot to an independently protected location, verify it, dry-run a restore into a new directory, perform the restore, then inspect the startup files and status. An in-place restore is exceptional and requires confirmation plus a rollback copy. Separately recover the independent repo, Zotero, data, and large assets; the project snapshot only covers the ResearchFlow workspace.

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

Every successful run directory contains `run.yaml`, `run.log`, `metrics.json`, and `environment.json`. Remote runs additionally retain `job.json`, `events.jsonl`, the exact `remote_runner.py` and its SHA-256, the submitted experiment card, and supervisor output when present. The run record links its experiment, level, command, exact commit, dirty flag/diff hash, configuration hash, environment, host/GPU request, metrics, artifacts, timestamps, and exit code. Fixture runs carry `test_only: true` and visible `TEST / MOCK` labels.

Remote collection is intentionally narrow: only small text/JSON/YAML provenance files are copied, with a 10 MiB limit per file. Datasets, checkpoints, videos, and remote worktrees remain on the server.

## Git-first boundary

The card captures a baseline commit. `rf experiment worktree` creates a detached worktree from that commit. Before execution, `preflight` checks the card, state, hypothesis, commit, clean/dirty state, config, modified paths, metrics, guardrails, stop conditions, command, tests, GPU count, and full approval. `--allow-dirty` is exceptional and provenance must preserve the diff hash.
