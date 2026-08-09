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

## Git-first boundary

The card captures a baseline commit. `rf experiment worktree` creates a detached worktree from that commit. Before execution, `preflight` checks the card, state, hypothesis, commit, clean/dirty state, config, modified paths, metrics, guardrails, stop conditions, command, tests, GPU count, and full approval. `--allow-dirty` is exceptional and provenance must preserve the diff hash.
