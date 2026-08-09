# Toy Research (TEST / MOCK)

This deterministic fixture verifies ResearchFlow plumbing without a GPU. It is not a scientific benchmark and its metrics must never be cited as research evidence.

The E2E test initializes this file as an independent Git repository, creates evidence-backed OBS/HYP/EXP records, modifies `MULTIPLIER` inside an experiment worktree, commits it, and executes smoke, pilot, and full levels. Each execution writes a real `metrics.json`; repeated score equality verifies reproducibility of the fixture only.
