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
rf evidence zotero configure [--base-url LOOPBACK_API] [--library users/0]
rf evidence zotero status|libraries|collections
rf evidence zotero search QUERY [--collection KEY] [--tag TAG] [--limit N]
rf evidence zotero show ITEM_KEY
rf evidence zotero bibliography ITEM_KEY... [--style CSL_STYLE] [--locale LOCALE]
rf evidence zotero link ITEM_KEY
rf evidence zotero refresh PAPER-ID
rf memory observation add|show
rf memory decision add|show
rf hypothesis new|show
rf daily
rf doctor
```

Zotero subcommands are read-only toward Zotero. Search/full-text indexing, collections/tags, attachments/annotations, and CSL formatting remain Zotero functions. `link` and `refresh` are the only ResearchFlow writes: they maintain a `PAPER-*` analysis/source reference and never copy Zotero PDFs. See [Zotero integration](zotero.md).

Experiment and run commands:

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

Compute commands:

```text
rf compute add NAME --type local|ssh --workspace-root PATH [--host ALIAS]
rf compute list
rf compute probe NAME [--dry-run]
rf compute status [NAME]
rf compute jobs
rf compute lock NAME --experiment EXP-0001 --job-id JOB-1
rf compute unlock NAME [--force --yes]
rf compute plan NAME --project-id ID --experiment EXP-ID --commit SHA --command CMD
rf compute submit NAME --project-id ID --experiment EXP-ID [--level smoke|pilot|full] [--dry-run] [--yes]
rf compute job NAME RUN-000001
rf compute collect NAME RUN-000001 --project-id ID [--dry-run]
```

`compute plan` is side-effect free. It shows the persistent remote repo/worktree/run layout and SSH steps; it never copies datasets, large checkpoints, or a whole repository.

`compute submit` checks the experiment card and pinned commit, creates a detached worktree in the configured remote workspace, and starts a background runner. A full run still requires `approval.full=approved` and `--yes`. `compute job` reads the remote job record. `compute collect` accepts only a terminal job, copies bounded provenance artifacts (maximum 10 MiB each), preserves the exact `remote_runner.py` with its SHA-256 in `run.yaml`, writes the standard local run record, appends the run/job registries, and advances the experiment state. Its `--dry-run` lists what would and would not be collected.

Remote execution does not upload a repository, datasets, checkpoints, or videos. The server repository at `<workspace-root>/repos/<project-id>` must already contain the experiment commit. Job transitions are preserved in remote `events.jsonl`; repeated status checks may also append duplicate observed states to the coordinator ledger.

Compute commands do not require a default research project. A live `compute probe` returns a non-zero exit code when the target is unreachable; `--dry-run` remains successful without opening a connection.
