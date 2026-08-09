# ResearchFlow

ResearchFlow is a local-first Research OS for AI-assisted scientific research. It preserves the evidence, observations, hypotheses, experiments, runs, decisions, and provenance that must survive a change of model, session, machine, or research direction.

The source of truth is ordinary YAML, Markdown, JSON, and JSONL files. ResearchFlow is the control plane; your research code remains in its own Git repository.

## Five-minute start

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
rf init --home C:\ResearchFlow
rf project add toy --repo C:\research\toy
rf status --project toy
```

The five commands to remember are `rf status`, `rf evidence`, `rf experiment`, `rf run`, and `rf doctor`.

Project workspaces live below the configurable research home in `.projects/<project-id>/`; research code is not copied there. An agent starts by reading the project workspace's `AGENTS.md`, `KNOWLEDGE.md`, and `memory/current-state.md`, then retrieves only task-relevant primary evidence.

See [architecture](docs/architecture.md), [concepts](docs/concepts.md), and [interface design](docs/interface-design.md). A complete command walkthrough is added as implementation phases become executable.

