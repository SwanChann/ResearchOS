---
name: hypothesis-focus
description: Convert an evidence-grounded unknown into one falsifiable, bounded hypothesis.
---

# Hypothesis Focus

1. State the focused question and retrieve observations, papers, repositories, formal matrix `XIDEA-*` records, and prior failed experiments.
2. Separate the observed phenomenon from candidate explanations and confounders.
3. Rank candidates by impact, falsifiability, feasibility, and evidence strength.
4. Select the smallest useful experiment and define falsification, stop-loss, and decision-relevant metrics.

Output: focused question, scope, HYP record content, evidence for/against, falsification condition, MVP experiment, and stop-loss. Use `rf hypothesis new --ideas XIDEA-*` when an Idea is a source so PAPER/claim provenance and novelty warnings survive. A literature-derived Hypothesis is not an Observation and must say local empirical support is unestablished. Write a Hypothesis record only; do not create a conclusion or start a run.
