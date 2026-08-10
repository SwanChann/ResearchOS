# Interface Design

This document freezes the small public surface before implementation.

## CLI

Top-level commands are limited to `init`, `project`, `status`, `evidence`, `memory`, `hypothesis`, `experiment`, `run`, `compute`, `daily`, and `doctor`. Subcommands name an object and one action; no lifecycle-manager hierarchy is exposed.

Core forms:

```text
rf init [--home PATH]
rf project add|list|show
rf status
rf evidence paper add|list|show|verify
rf evidence repo add|list|show|search
rf evidence search QUERY
rf evidence zotero configure|status|libraries|collections|search|show|bibliography|link|refresh
rf memory observation add|show
rf memory decision add|show
rf hypothesis new|show
rf experiment new|show|transition|approve|preflight|worktree|smoke|pilot|full
rf run show|logs|artifacts
rf compute add|list|probe|status|jobs|lock|unlock|plan|submit|job|collect
rf daily
rf doctor
```

Commands that create worktrees, execute runs, collect artifacts, touch remote machines, or unlock compute expose `--dry-run` where meaningful. Remote submit creates a detached worktree from a pinned commit; remote collect registers only bounded provenance artifacts. Full runs and force-unlock require explicit confirmation flags.

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

Global configuration contains only the research root, defaults, machine aliases, and preferences. Each project workspace contains `project.yaml`, `AGENTS.md`, `KNOWLEDGE.md`, memory records, evidence indexes, experiment cards/registry/reports, run records/artifacts, and daily notes. The research repo is referenced by path.

## Record contracts

JSON Schemas define Project, Observation, Hypothesis, Experiment, Run, and Decision. Paper and RepositoryEvidence use validated YAML/frontmatter records. A Zotero-linked Paper stores a minimal bibliographic snapshot and stable source reference but no copied PDF. Markdown records combine YAML frontmatter with fixed human-readable sections.

Experiment cards are authoritative; `experiments/registry.jsonl` records append-only state events. Each run has an authoritative `runs/<RUN-ID>/run.yaml`; the run registry is an index/event log.

## Skill contract

Each `skills/<name>/SKILL.md` declares purpose, required inputs/retrieval, prohibited behavior, steps, output contract, and write-back rules. Skills are instructions readable by any capable agent, not executable plugins.

## No duplicate interfaces

`memory observation add` and `memory decision add` remain grouped instead of adding `observe`/`decide` aliases. State changes use one `experiment transition` primitive; `smoke`, `pilot`, and `full` are execution commands with gate checks, not aliases for arbitrary transitions.

Zotero operations stay under `evidence zotero`: Zotero owns retrieval, organization, attachment/annotation context, and citation formatting; ResearchFlow `link` is the single handoff into a `PAPER-*` analysis.

`evidence paper verify` is the explicit completion gate for a primary-source deep read. It checks the Markdown contract and records only the inspected document's fingerprint/version/page basis plus searchable analysis labels; it does not copy or mutate the Zotero-owned PDF.
