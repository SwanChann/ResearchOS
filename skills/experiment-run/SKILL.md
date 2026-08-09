---
name: experiment-run
description: Execute only an approved, preflighted Experiment Card and register complete provenance.
---

# Experiment Run

1. Read the approved card; do not alter its question, baseline, metric, or scope.
2. Run preflight, enforce budget and the single-GPU lock, then execute SMOKE, PILOT, or approved FULL.
3. Collect `run.log`, `metrics.json`, `environment.json`, and `run.yaml`; register success and failure alike.
4. Confirm the Run links exact commits, config/dataset hashes, hardware, timestamps, exit code, and artifacts.

Never run FULL without human approval and explicit confirmation. Never delete a failed experiment or claim a run completed before `REGISTERED`. Stop on configured conditions.
