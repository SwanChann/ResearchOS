# ADR-0003: Bounded compute and explicit single-GPU locks

Status: accepted

## Decision

V0.2 supports one active heavy job per configured machine/GPU. Local execution uses an inspectable YAML lock and append-only coordinator job ledger. SSH execution uses an atomic server-side lock directory, a current-state `job.json`, and append-only `events.jsonl`. Remote repositories, detached worktrees, and run directories are persistent; no daemon or distributed scheduler is introduced.

## Consequences

Lock owner, PID, host, job, experiment, and start time are visible. The server obtains exclusivity with atomic directory creation and releases only a lock whose owner matches the run. Local stale locks are detected but never silently removed; active force-unlock needs explicit confirmation and external GPU-process verification. The protocol coordinates cooperating ResearchFlow clients, but cannot protect against unrelated tools that ignore the lock. Remote cancellation and automatic retention cleanup remain out of scope.
