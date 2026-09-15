# Interface Design

This document freezes the small public surface before implementation.

## CLI

The public surface remains object/action oriented. Durability and registry features add the explicit top-level objects `snapshot`, `artifact`, `knowledge`, `scaffold`, `preflight`, and `migrate`; they do not introduce a daemon, database, or hidden automation.

Core forms:

```text
rf init [--home PATH]
rf project add|list|show
rf status
rf snapshot create|list|show|verify|restore
rf evidence paper add|list|show|verify|review
rf evidence matrix templates|axes|init|add|synthesize|migrate|review|validate|render|show
rf evidence repo add|list|show|search
rf evidence problem add|list|show
rf evidence claim add|list|show
rf evidence corpus create|list|show|verify|status|add-extraction|review-extraction
rf evidence adjacency build|add|list|show|neighbors|explain|review|check|export|promote
rf evidence gap detect|list|show|review
rf evidence graph connect|rebuild|check|show|audit|review-input|review|export
rf evidence search QUERY
rf evidence zotero configure|status|doctor|libraries|collections|search|show|bibliography|link|refresh
rf artifact add|list|show|verify|refresh|supersede|migrate
rf knowledge rebuild|check
rf scaffold paper-analysis|matrix-entry|synthesis-idea|artifact|problem|claim|corpus-extraction|graph-review
rf preflight paper-analysis|matrix-entry|matrix-synthesis|artifact|problem|claim|corpus-extraction|graph-review FILE
rf migrate paper-verification|corpus-gap-evidence-graph
rf memory observation add|show
rf memory decision add|show
rf hypothesis new|show
rf experiment new|show|transition|approve|preflight|worktree|smoke|pilot|full
rf run show|logs|artifacts
rf compute add|list|probe|status|jobs|lock|unlock|plan|submit|job|collect
rf daily
rf doctor [--probe-machines]
```

Commands that create worktrees, execute runs, collect artifacts, touch remote machines, or unlock compute expose `--dry-run` where meaningful. Remote submit creates a detached worktree from a pinned commit; remote collect registers only bounded provenance artifacts. Full runs and force-unlock require explicit confirmation flags.

Ordinary `doctor` is a local integrity check. Live local/SSH machine probes require the explicit `--probe-machines` flag so an audit cannot contact external systems as a hidden side effect. `project show` exposes the resolved workspace and new-session startup files; global `--project ID` selection works independently of the current working directory.

## Python API

```python
from researchflow import ResearchProject

project = ResearchProject.open("embodied-nav")
project.status()
project.evidence.search("temporal context")
project.experiments.get("EXP-0023")
```

Only `ResearchProject` is a stable convenience facade in V0.1. Lower-level modules are internal and kept functional.

## Filesystem contracts

Global configuration contains only the research root, defaults, machine aliases, and preferences. Each project workspace contains authoritative records plus `.research/artifacts.yaml`; the research repo and Zotero remain referenced external authorities. Snapshot manifests name those boundaries without claiming external assets were copied.

## Record contracts

JSON Schemas define Project, Observation, Hypothesis, Experiment, Run, and Decision. Paper and RepositoryEvidence use validated YAML/frontmatter records. A Zotero-linked Paper stores a minimal bibliographic snapshot and stable source reference but no copied PDF. Markdown records combine YAML frontmatter with fixed human-readable sections.

Experiment cards are authoritative; `experiments/registry.jsonl` records append-only state events. Each run has an authoritative `runs/<RUN-ID>/run.yaml`; the run registry is an index/event log.

## Skill contract

Each `skills/<name>/SKILL.md` declares purpose, required inputs/retrieval, prohibited behavior, steps, output contract, and write-back rules. Skills are instructions readable by any capable agent, not executable plugins.

## No duplicate interfaces

`memory observation add` and `memory decision add` remain grouped instead of adding `observe`/`decide` aliases. State changes use one `experiment transition` primitive; `smoke`, `pilot`, and `full` are execution commands with gate checks, not aliases for arbitrary transitions.

Zotero operations stay under `evidence zotero`: Zotero owns retrieval, organization, attachment/annotation context, and citation formatting; ResearchFlow `link` is the single handoff into a `PAPER-*` analysis.

`evidence paper verify` is the explicit source/fingerprint gate, while `paper review` is a separate human semantic action scoped to a fingerprint. Neither state is named or reported as reproduction or scientific establishment.

`evidence matrix` manages one project-level `.research/literature_matrix.md`. YAML frontmatter is the authoritative structured record; the Markdown comparison tables are a deterministic view. `add` accepts one YAML paper entry, requires a verified `PAPER-*`, rejects duplicate papers or missing/unknown axes, and validates every supported cell's page and claim references before an atomic rewrite. `synthesize` consumes a separate schema-checked update in `replace` or `upsert` mode, verifies every cross-paper claim reference, writes atomically, and treats an unchanged replay as a no-op.

Matrix axes come from a named template or confirmed project YAML. They lock after first insertion. `migrate` is the only supported semantic axes change and preserves superseded values/evidence. Artifact paths are confined to the project workspace; Knowledge is a generated view, not an alternative authority.

`PROB-*` and `CLAIM-*` are Markdown records with validated YAML frontmatter. Claim import is always `draft` and requires exact Finding, Run, Artifact hash, JSON Pointer, metric value, scope, and qualifier fields. `.research/evidence-graph/edges.yaml` is an authoritative typed relation ledger; `.research/evidence-graph/index.json` is a rebuildable projection. Graph L1 checks are deterministic. Missing or unavailable L2 semantic review fails closed and cannot produce `evidence_ready`.

`CORPUS-*` freezes matrix and paper fingerprints; per-paper extraction files preserve structured tuples and locators. `CGAPRUN-*` records deterministic motif inputs and marks fixtures with `test_only`. `GAP-*` remains a candidate until a non-empty `human:*` reviewer explicitly approves its current fingerprint. L2/L3 review and 0.5.0 migration are file-driven, preflightable, and snapshot/fingerprint gated rather than provider-coupled.
