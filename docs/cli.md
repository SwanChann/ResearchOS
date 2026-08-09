# CLI Reference

Run `rf --help` for the installed version's authoritative surface. Commands accept a global `--project ID`; when omitted, ResearchFlow uses `default_project` or the only configured project.

Available in the human-interface phase:

```text
rf init --home PATH
rf project add ID --repo PATH [--name NAME]
rf project list|show
rf status
rf evidence paper add PDF --title TITLE [metadata]
rf evidence paper list|show
rf evidence repo add --name NAME --commit SHA (--url URL | --local PATH)
rf evidence repo list|show|search
rf evidence search QUERY
rf memory observation add|show
rf memory decision add|show
rf hypothesis new|show
rf daily
rf doctor
```

`experiment`, `run`, and `compute` are stable top-level names; their executable actions are added by subsequent lifecycle phases.
