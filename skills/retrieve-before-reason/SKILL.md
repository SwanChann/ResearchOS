---
name: retrieve-before-reason
description: Ground research claims in task-appropriate local and primary evidence before reasoning.
---

# Retrieve Before Reason

## Required input

A research question and the active project workspace.

## Protocol

1. Classify the question as project history, literature, novelty/latest, code implementation, or experimental claim.
2. Read `AGENTS.md`, `KNOWLEDGE.md`, and `memory/current-state.md`; retrieve only task-relevant IDs/files.
3. Project history: follow Decision -> Experiment/Run -> Observation. Literature: local index -> analysis -> original PDF. Code: pinned repository and exact commit. Latest/novelty: local KB plus live search. Experiment: registered run -> raw metrics/config/commits.
4. Inspect a primary source when the claim depends on exact method, code, metric, or current status.
5. Label the durable output as Verified Literature, Verified Code, Project Observation, Experimental Result, Hypothesis, Agent Inference, or Needs Verification.

## Prohibited

Do not treat model memory, a search snippet, an unpinned repository, smoke output, or a fixture as scientific evidence. Do not invent a citation or fill missing results with plausible values.

## Output and write-back

Return relevant IDs, verified facts with provenance, inferences, conflicts/gaps, and what could change the answer. Write durable new facts to an evidence or memory record; do not dump the whole answer into `current-state.md`.
