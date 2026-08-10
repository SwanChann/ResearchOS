# ADR-0005: Live machine probes require explicit intent

Status: accepted

## Context

ResearchFlow stores local and SSH machine aliases in global configuration. Earlier `rf doctor` behavior probed every configured machine while performing what otherwise appeared to be a local integrity audit. That could open an SSH connection, depend on VPN state, prompt for credentials, or report an unrelated remote outage as a local system failure.

## Decision

- `rf doctor` validates configuration shape, project paths, schemas, references, IDs, startup files, skills, and local tool availability without probing machines.
- Configured machines are reported as deliberately skipped.
- `rf doctor --probe-machines` is the explicit combined local/SSH liveness check.
- `rf compute probe NAME [--dry-run]` remains the narrow per-machine interface.

## Consequences

- A normal system or project audit has no hidden network side effect.
- Connectivity and GPU availability are a separate, time-dependent operational claim.
- A user or agent must have current authorization and the required VPN/network state before selecting a live probe.
- The DoD can verify compute contracts and TEST/MOCK coordination without claiming that a real GPU is currently available.
