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

Experiment and local-run commands:

```text
rf experiment new --hypothesis HYP-0001 --title ... --question ...
                  --command ... --allowed-paths ... --frozen-paths ...
                  --primary ... --secondary ... --guardrails '{...}'
                  --stop-conditions ... [--test-only]
rf experiment show|transition|worktree|preflight
rf experiment smoke|pilot|full
rf experiment approve EXP-0001 --level full --yes
rf run show|logs|artifacts RUN-000001
```

`compute` remains a stable top-level name; executable machine and lock actions are added by the remote-compute phase.
