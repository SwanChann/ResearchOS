---
name: experiment-design
description: Create a bounded Experiment Card from an approved hypothesis; never execute it.
---

# Experiment Design

Retrieve the HYP record and linked primary evidence. Define baseline repository/commit/config, one isolated change, allowed/frozen paths, primary and secondary metrics, guardrails, SMOKE/PILOT/FULL budgets, stop conditions, compute needs, approvals, required tests, and run command.

Reject designs with no evidence, missing falsification, one metric only, unbounded runs, dirty baseline, data leakage, or ambiguous configuration. Output and validate one `EXP-*` card in `DRAFT`; do not implement or run it.
