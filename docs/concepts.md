# Core Concepts

```text
Project
  +-- Evidence (Paper, RepositoryEvidence, web reference)
  +-- Problem -- stable objective, scope, constraints, and application context
  +-- Artifact -- registered project product with file hash and lineage
  +-- Observation -- describes what happened
  |       +-- Hypothesis -- falsifiable explanation, never a fact
  |               +-- Experiment -- approved question, scope, budget, metrics
  |                       +-- Run -- one execution with raw provenance
  |                               +-- Observation
  |                                       +-- Claim -- bounded statement linked to exact metric evidence
  +-- Decision -- human/policy choice linked back to evidence and runs
```

## Epistemic labels

Research records distinguish Verified Literature, Verified Code, Project Observation, Experimental Result, Hypothesis, Agent Inference, and Needs Verification. A claim without provenance is not accepted as a research conclusion.

Retrieval precedes reasoning. Project questions retrieve decisions, experiments, and observations; literature questions retrieve the local index and primary paper; implementation questions inspect the pinned source commit; current/novelty questions add live search; experimental claims require a registered run, raw metrics, configuration, and commits.

Smoke verifies plumbing only. Pilot provides a limited directional signal. Full runs require approval. A better metric may support a recommendation but does not itself create a Decision or prove a hypothesis.

## Entity identity

Human-facing IDs are monotonic and stable: `PAPER-0001`, `REPO-0001`, `CORPUS-0001`, `PROB-0001`, `GAP-0001`, `OBS-0001`, `HYP-0001`, `EXP-0001`, `RUN-000001`, `CLAIM-0001`, `DEC-0001`, `ARTIFACT-0001`, `CGAPRUN-000001`, and `EGAUDIT-000001`. Matrix ideas use `XIDEA-*` and may be promoted explicitly into a Hypothesis while preserving their PAPER/claim references. A Gap-derived Hypothesis preserves the approved Gap fingerprint and reviewer. Neither route masquerades as an Observation or local empirical support.

## Verification and review layers

`contract_valid` means required fields and relationships pass machine checks. `source_verified` and `fingerprint_verified` bind an analysis to an identified source. `human_reviewed` means a named reviewer accepted only the recorded scope for the current fingerprint. These states do not imply reproduction, novelty, causal support, or scientific truth; those boundaries remain visible as `reproduction_unverified` and `scientific_claim_unestablished`.

Artifact SHA-256 verification establishes file integrity only. Smoke establishes plumbing only. Agent-generated scaffolds are drafts until they pass preflight and any required human review.

EvidenceGraph is a project-specific term for the typed relation ledger plus its rebuildable index. L1 means deterministic structure and exact metric checks; L2 means scoped semantic consistency; L3 means implementation/reproduction fidelity. L1 alone never upgrades a Claim to scientific truth, and unavailable L2 review is not a pass.

CorpusGap separates four states that are easy to conflate: a verified paper source, a locator-bound Agent extraction, a human-accepted extraction, and a human-approved candidate Gap. Deterministic motifs and heuristic scores help triage; they do not establish novelty or an open scientific problem.
