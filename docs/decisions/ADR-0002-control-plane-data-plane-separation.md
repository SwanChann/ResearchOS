# ADR-0002: Separate control plane from research repositories

Status: accepted

## Decision

ResearchFlow project workspaces reference, but do not contain or copy, the independent research code repository. Git worktrees are created beside or under a configured worktree root.

## Consequences

Research assets and executable code have clear ownership and Git histories. Provenance records must capture both paths and commits. Dataset and checkpoint locations remain references rather than synchronized assets.

