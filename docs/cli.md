# CLI Reference

Run `rf --help` for the installed version's authoritative surface. Commands accept a global `--project ID`; when omitted, ResearchFlow uses `default_project` or the only configured project.

Available in the human-interface phase:

```text
rf init --home PATH
rf project add ID --repo PATH [--name NAME]
rf project list
rf project show [ID]
rf status [--verbose]
rf snapshot create|list|show|verify|restore
rf evidence paper add PDF --title TITLE [metadata]
rf evidence paper list|show
rf evidence paper verify PAPER-ID --sha256 HEX --source-version VERSION --pages N
                         --core-operator TEXT --primary-logic TEXT --methods CSV
rf evidence paper review PAPER-ID --reviewer NAME --decision accepted|revision_requested|rejected --scope TEXT
rf evidence matrix templates list|show
rf evidence matrix axes scaffold|validate|confirm
rf evidence matrix init --title TITLE --scope SCOPE [--template NAME | --axes-file YAML]
rf evidence matrix add ENTRY.yaml
rf evidence matrix synthesize UPDATE.yaml
rf evidence matrix migrate MIGRATION.yaml [--dry-run]
rf evidence matrix review --reviewer NAME --decision DECISION --scope TEXT
rf evidence matrix validate|render|show
rf evidence repo add --name NAME --commit SHA (--url URL | --local PATH)
rf evidence repo list|show|search
rf evidence problem add REQUEST.yaml [--dry-run]
rf evidence problem list|show
rf evidence claim add REQUEST.yaml [--dry-run]
rf evidence claim list|show|supersede
rf evidence corpus create|list|show|verify|status|add-extraction|review-extraction
rf evidence adjacency build|add|list|show|neighbors|explain|review|check|export|promote
rf evidence gap detect --corpus ID --motifs FILE [--test-only] [--dry-run]
rf evidence gap list|show|review
rf evidence graph connect --from ID --relation RELATION --to ID [--provenance IDS] [--dry-run]
rf evidence graph rebuild [--dry-run]
rf evidence graph check [--strict]
rf evidence graph show --claim CLAIM-ID
rf evidence graph audit --claim CLAIM-ID [--mode full-chain] [--dry-run]
rf evidence graph review-input --claim CLAIM-ID
rf evidence graph review --claim CLAIM-ID --file REVIEW.yaml [--dry-run]
rf evidence graph export --output PATH [--format dot|json] [--dry-run]
rf evidence search QUERY
rf evidence zotero configure [--base-url LOOPBACK_API] [--library users/0]
rf evidence zotero status [--verbose]
rf evidence zotero doctor [--item-key KEY]
rf evidence zotero libraries|collections
rf evidence zotero search QUERY [--collection KEY] [--tag TAG] [--limit N]
rf evidence zotero show ITEM_KEY
rf evidence zotero bibliography ITEM_KEY... [--style CSL_STYLE] [--locale LOCALE]
rf evidence zotero link ITEM_KEY
rf evidence zotero refresh PAPER-ID
rf memory observation add|show
rf memory decision add|show
rf artifact add|list|show|verify|refresh|supersede|migrate
rf knowledge rebuild [--dry-run]
rf knowledge check
rf scaffold paper-analysis|matrix-entry|synthesis-idea|artifact|problem|claim|corpus-extraction|paper-adjacency|graph-review
rf preflight paper-analysis|matrix-entry|matrix-synthesis|artifact|problem|claim|corpus-extraction|paper-adjacency|graph-review FILE
rf migrate paper-verification [--dry-run]
rf migrate corpus-gap-evidence-graph --dry-run [--snapshot-dir DIR]
rf migrate corpus-gap-evidence-graph --plan-fingerprint SHA256 [--snapshot-dir DIR]
rf hypothesis new|show [--ideas XIDEA-0001,...] [--gap GAP-0001]
rf daily
rf doctor [--strict] [--probe-machines]
```

Snapshot creation defaults to `<research-home>/.snapshots/<project-id>` and accepts `--output-dir`. `verify` checks manifest integrity plus missing, extra, size-changed, and hash-changed members. Restore defaults to a new target, prevents traversal/absolute-path escape, and performs no writes with `--dry-run`. In-place restore requires `--in-place --yes` and preserves a sibling rollback copy. Snapshot manifests identify external authorities but do not claim they were backed up.

`project add/show/status` report the workspace/repo boundary, reachability, Git repository, branch/detached state, HEAD/unborn state, commit/checkpoint, tracked modifications, untracked files, and snapshot availability. `doctor` emits PASS/WARN/FAIL; warnings preserve exit code 0 unless `--strict` is supplied.

`--project ID` is resolved through the global ResearchFlow configuration and is independent of the shell's current directory. `project show ID` prints the resolved workspace, the new-session startup files, and an explicit status command. Prefer explicit project selection whenever more than one topic exists.

Zotero subcommands are read-only toward Zotero. Search/full-text indexing, collections/tags, attachments/annotations, and CSL formatting remain Zotero functions. `link`, `refresh`, and `paper verify` write only ResearchFlow analysis/provenance records and never copy or modify Zotero PDFs. See [Zotero integration](zotero.md).

After primary-source inspection, `paper verify` validates the page-cited deep-read contract and records its source fingerprint. It emits explicit contract/source/fingerprint/human-review/reproduction/scientific-claim states. `paper review` records a named, scoped human decision against that fingerprint. Reverification with another fingerprint makes the old review stale.

The literature matrix lives at `.research/literature_matrix.md`. New matrices default to the `generic` template; `embodied-navigation` preserves the historical 12 axes. Confirmed project YAML is also accepted. Axes lock after the first paper. `matrix migrate` previews an explicit old→new mapping, snapshots before writes, retains unmapped cells/evidence as superseded provenance, and is idempotent on replay.

Artifact commands operate on `.research/artifacts.yaml`. Registered paths must resolve inside the project workspace. `verify` checks existence, hash, and linked IDs only. `refresh` deliberately accepts a new file hash; `supersede` retains the historical file and bidirectional chain. `artifact migrate --scan PATH --dry-run` lists legacy candidates without changing them; a real migration creates a snapshot and registers them as drafts.

`knowledge rebuild` replaces only the delimited generated region and is idempotent. `knowledge check` reports stale registry coverage, broken links, and superseded-current mistakes. Concise `status` includes registry counts; `status --verbose` exposes individual entries and artifact integrity.

Problem, Claim, extraction, and graph-review scaffolds are Agent-editable drafts. `preflight claim` requires exact registered metric evidence and does not call a model or external service. `graph connect` adds a typed edge only when endpoint records and relation-specific references agree; reconnecting changed endpoints creates a new fingerprint-bound edge and preserves the old one as superseded. `graph rebuild` writes only the disposable index. `graph review` imports an explicit fingerprint-bound L2/L3 result; it never silently invokes a provider. `graph check --strict` remains non-zero until required review passes.

Corpus creation freezes the selected matrix fingerprint and each included paper source fingerprint. Extraction acceptance and Gap approval are explicit human gates. Gap detection is deterministic for a fixed Corpus, accepted extraction set, motif version, and `test_only` flag. Migration only maps exact legacy references, creates no inferred Problem/Gap/Claim, requires the reviewed dry-run fingerprint, and verifies a snapshot before authority files change.

Paper adjacency build accepts only a valid Corpus with current human-accepted extraction for every Paper. It creates deterministic candidates from shared Task, Method, Assumption, Dataset, Metric, and explicit failure structure. `neighbors` defaults to current accepted edges; `review --decision accepted` requires `human:*`. Manual/Agent semantic proposals use scaffold→preflight→add and must cite both Papers' Claim IDs and locators. `promote` explicitly creates a fingerprint-bound EvidenceGraph PAPER edge with PADJ provenance. Adjacency-aware Gap motifs consume only current accepted PADJ records.

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

`rf doctor` performs local integrity checks by default and reports configured machines as skipped. `rf doctor --probe-machines` is an explicit live operation that may execute `nvidia-smi` locally or contact configured SSH hosts. Use it only with current authorization and the required network/VPN state. `evidence zotero doctor` is a separate loopback-only diagnostic and performs GET requests only.
