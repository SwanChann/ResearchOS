---
name: experiment-review
description: Review an Experiment Card for validity, fairness, scope, leakage, budget, and reproducibility before compute.
---

# Experiment Review

Run `rf experiment preflight EXP-ID --level LEVEL` and independently check:

- baseline fairness and exact commit/config;
- confound isolation and allowed/frozen paths;
- primary, secondary, guardrail, and failure-case metrics;
- dataset leakage and manifest identity;
- required tests, command, environment, artifact contract;
- bounded run/GPU budget and stop conditions;
- level-specific approval.

Output PASS/BLOCKED with each failure, evidence, and a concrete fix. A smoke pass proves plumbing only. Do not weaken metrics or scope merely to pass review.
