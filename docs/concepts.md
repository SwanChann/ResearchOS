# Core Concepts

```text
Project
  +-- Evidence (Paper, RepositoryEvidence, web reference)
  +-- Observation -- describes what happened
  |       +-- Hypothesis -- falsifiable explanation, never a fact
  |               +-- Experiment -- approved question, scope, budget, metrics
  |                       +-- Run -- one execution with raw provenance
  |                               +-- Observation
  +-- Decision -- human/policy choice linked back to evidence and runs
```

## Epistemic labels

Research records distinguish Verified Literature, Verified Code, Project Observation, Experimental Result, Hypothesis, Agent Inference, and Needs Verification. A claim without provenance is not accepted as a research conclusion.

Retrieval precedes reasoning. Project questions retrieve decisions, experiments, and observations; literature questions retrieve the local index and primary paper; implementation questions inspect the pinned source commit; current/novelty questions add live search; experimental claims require a registered run, raw metrics, configuration, and commits.

Smoke verifies plumbing only. Pilot provides a limited directional signal. Full runs require approval. A better metric may support a recommendation but does not itself create a Decision or prove a hypothesis.

## Entity identity

Human-facing IDs are monotonic and stable: `PAPER-0001`, `REPO-0001`, `OBS-0001`, `HYP-0001`, `EXP-0001`, `RUN-000001`, and `DEC-0001`. Allocation is atomic within one ResearchFlow home and never renumbers existing records.

