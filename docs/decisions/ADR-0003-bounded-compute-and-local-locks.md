# ADR-0003: Bounded compute and explicit single-GPU locks

Status: accepted

## Decision

V0.1 supports one active heavy job per configured machine/GPU through an inspectable YAML lock and append-only job ledger. Remote execution is represented as a persistent-repo SSH plan; no daemon or distributed scheduler is introduced.

## Consequences

Lock owner, PID, host, job, experiment, and start time are visible. Stale locks are detected but never silently removed. Active force-unlock needs explicit confirmation and external GPU-process verification. A coordinator-local lock cannot protect against unrelated tools that ignore ResearchFlow; a future server-side lock protocol is required before multi-client remote execution is considered production-safe.
