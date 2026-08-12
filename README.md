# ResearchFlow

ResearchFlow is a local-first Research OS for AI-assisted scientific research. It preserves the evidence, observations, hypotheses, experiments, runs, decisions, and provenance that must survive a change of model, session, machine, or research direction.

The source of truth is ordinary YAML, Markdown, JSON, and JSONL files. ResearchFlow is the control plane; your research code remains in its own Git repository. It is not a chat-history store, autonomous paper generator, or multi-agent framework.

## Why use it?

Research code alone cannot answer why a direction was paused, which source supports an implementation claim, whether a metric came from a clean commit, or what a failed run taught you. ResearchFlow makes those links durable and inspectable while keeping the human in control of full runs, merges, pushes, destructive actions, and real-robot work.

## Five-minute start

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\rf init --home C:\ResearchFlow
.venv\Scripts\rf project add embodied-nav --repo C:\research\embodied-nav
.venv\Scripts\rf status
```

Linux/macOS uses `.venv/bin/python` and `.venv/bin/rf`. The project uses a standard `pyproject.toml`; `uv sync` is also compatible when uv is available, but is not required.

The core commands to remember are:

```text
rf status       current question, HYP/EXP/RUN state, next action
rf evidence     Zotero-linked paper analysis and pinned-code evidence
rf experiment   card, worktree, preflight, bounded execution
rf run          provenance, logs, metrics, artifacts
rf doctor       local config, schemas, tools, paths, references, IDs
rf snapshot     verifiable workspace recovery copies
rf artifact     registered project products and file integrity
rf knowledge    generated navigation that preserves manual prose
```

## Zotero literature boundary

Zotero Desktop is the recommended authority for bibliographic metadata, collections/tags, PDFs, notes/annotations, and citation formatting. ResearchFlow connects to Zotero's official loopback Local API with read-only `GET` requests and stores only a minimal source reference plus project-specific analysis and evidence relationships.

```powershell
rf evidence zotero configure --library users/0
rf evidence zotero status
rf evidence zotero search "visual navigation"
rf evidence zotero show ITEMKEY
rf evidence zotero link ITEMKEY
# Edit the PAPER-* analysis after reading the primary PDF, then finalize it:
rf evidence paper verify PAPER-0001 --sha256 HEX --source-version VERSION --pages N --core-operator TEXT --primary-logic TEXT --methods method-a,method-b
# Build a reproducible cross-paper comparison after individual verification:
rf evidence matrix templates list
rf evidence matrix init --title "Navigation literature" --scope "Verified primary PDFs" --template embodied-navigation
rf scaffold matrix-entry PAPER-0001 --output .\PAPER-0001.matrix-entry.yaml
rf preflight matrix-entry .\PAPER-0001.matrix-entry.yaml
rf evidence matrix add .\PAPER-0001.matrix-entry.yaml
rf evidence matrix synthesize .\corpus-synthesis.yaml
rf evidence matrix validate
```

The default matrix template is cross-domain `generic`; the historical 12-axis contract is named `embodied-navigation`. Project axes must be confirmed before initialization, lock after the first paper, and change only through an explicit previewable migration. `matrix synthesize` accepts a schema-checked YAML file with evidence-linked `syntheses`/`ideas`. Invalid paper or claim references are rejected before the atomic rewrite; replaying an unchanged update is idempotent. Linking creates a `PAPER-*` analysis record but does not copy the PDF. See [Zotero integration](docs/zotero.md) and [ADR-0004](docs/decisions/ADR-0004-zotero-literature-authority.md).

## Durability and authority boundaries

ResearchFlow files, Git history, and a complete backup solve different problems:

- The project workspace is the authority for research-control records.
- The independent repository is the authority for executable code; a clean Git commit is a code checkpoint, not a backup of the separate workspace.
- `rf snapshot create` creates a verified copy of one project workspace. Its manifest references, but does not copy, the repo, Zotero PDFs, datasets, weights, or large run assets.
- A private Git remote may provide an off-machine copy of text history, but GitHub is optional and is not a complete backup.
- A complete recovery plan separately protects the ResearchFlow home/global configuration, Zotero database and attachments, repositories, and non-Git assets, then proves them with a restore drill.

```powershell
rf --project my-project snapshot create --output-dir E:\ResearchFlowBackups
rf --project my-project snapshot verify E:\ResearchFlowBackups\my-project-....rfsnapshot
rf --project my-project snapshot restore SNAPSHOT --target C:\RestoreDrill\my-project --dry-run
rf --project my-project snapshot restore SNAPSHOT --target C:\RestoreDrill\my-project
```

In-place restore requires both `--in-place` and `--yes` and first creates a recoverable sibling backup. Optional config export is explicitly requested with `--include-redacted-config`; secrets are never exported raw.

## Artifacts, review, and navigation

Use `rf artifact add/list/show/verify/refresh/supersede` for reports, audit manifests, annotation protocols, and other project products. Artifact verification checks file existence, SHA-256, and record references only—it is not semantic or scientific verification. `rf knowledge rebuild` refreshes only the delimited generated region of `KNOWLEDGE.md`; manual text outside it remains untouched.

Paper and matrix outputs distinguish contract validity, source/fingerprint verification, human semantic review, reproduction, and scientific conclusion. A current accepted human review is scoped to the reviewed fingerprint; changing a PDF fingerprint or matrix content makes it stale. Even a current human review leaves `reproduction_unverified` and `scientific_claim_unestablished` true.

For a configured SSH target, the bounded remote lifecycle is:

```powershell
rf compute submit server4090 --project-id my-project --experiment EXP-0001 --level smoke --dry-run
rf compute submit server4090 --project-id my-project --experiment EXP-0001 --level smoke
rf compute job server4090 RUN-000001
rf compute collect server4090 RUN-000001 --project-id my-project --dry-run
rf compute collect server4090 RUN-000001 --project-id my-project
```

The server must already contain the project repository at `<workspace-root>/repos/<project-id>` and the pinned commit must be available there. ResearchFlow creates a detached worktree, launches the approved command in the background, records an append-only job event ledger, and collects only bounded text/JSON provenance artifacts.

## Where files live

```text
~/.researchflow/config.yaml
<research-home>/.projects/embodied-nav/
  project.yaml       # points to the independent code repository
  policy.yaml        # human/agent permission boundary
  AGENTS.md
  KNOWLEDGE.md
  skills/
  memory/{current-state.md,observations/,hypotheses/,decisions/}
  evidence/{papers/,repos/}
  .research/{literature_matrix.md,artifacts.yaml}
  experiments/{cards/,registry.jsonl,reports/}
  runs/{registry.jsonl,RUN-*/}
  notes/daily/
```

No database is authoritative. Datasets and large checkpoints stay in their configured local/remote locations; run records contain references and hashes where practical.

## Use from any folder or a new chat

ResearchFlow resolves projects from its global configuration, not from the current working directory. Use an explicit project ID so records cannot accidentally enter the wrong topic:

```powershell
& F:\codespace\ResearchOS\.venv\Scripts\rf.exe project show embodied-nav
& F:\codespace\ResearchOS\.venv\Scripts\rf.exe --project embodied-nav status
```

`project show` prints the project workspace and the three startup files a new agent must read. A new chat treats previous chat/model memory as a locator, not as verified project state: it rebuilds the current state from durable records, current Git state, and task-relevant primary evidence. See [cross-folder and new-session usage](docs/cross-folder-session-usage.md), [continue an existing project](docs/prompts/continue-existing-project.md), and [start a new topic](docs/prompts/start-new-topic.md).

## Human workflow: problem to decision

The following is a realistic shape, not a claim that any navigation result exists:

```powershell
rf evidence paper add .\papers\method.pdf --title "Method" --year 2026 --tags navigation,diffusion
rf evidence repo add --name OfficialCode --url https://example.invalid/repo --commit abc123 --papers PAPER-0001

rf memory observation add --title "Delayed right turns" --text "Observed on the registered route review." --evidence RUN-000001
rf hypothesis new --title "Temporal context" --statement "Bounded context may reduce the delay." --observations OBS-0001 --papers PAPER-0001 --ideas XIDEA-0001 --falsification "Pilot fails the turning metric or violates a guardrail."

rf experiment new --hypothesis HYP-0001 --title "Bounded temporal context" --question "Does it improve turning without collision regression?" --command "python train.py --config configs/temporal.yaml" --allowed-paths src/navigation,configs/temporal.yaml --frozen-paths evaluation,datasets,src/control --primary turning_success_rate --secondary success_rate,SPL --guardrails '{"collision_rate_max_increase_pp":1,"latency_max_increase_pct":10}' --stop-conditions loss_nan,oom_twice,max_runs
rf experiment worktree EXP-0001 --dry-run
# Create the worktree, implement only the allowed change, test, and commit it.
rf experiment transition EXP-0001 EVIDENCE_READY
rf experiment transition EXP-0001 HYPOTHESIS_APPROVED
rf experiment transition EXP-0001 IMPLEMENTED
rf experiment preflight EXP-0001 --level smoke
rf experiment smoke EXP-0001
rf experiment pilot EXP-0001
rf experiment approve EXP-0001 --level full --yes
rf experiment full EXP-0001 --yes

rf run show RUN-000003
rf memory observation add --title "Bounded pilot/full result" --text "Describe only what registered metrics show, with uncertainty." --evidence RUN-000003 --confidence medium
rf experiment transition EXP-0001 DECIDED
rf memory decision add --text "Accept, reject, pause, or follow up" --why "Evidence-bounded rationale" --evidence EXP-0001,OBS-0002,RUN-000003
```

Smoke validates plumbing only. Pilot is a bounded directional signal. A better primary metric does not prove the hypothesis and never creates a Decision automatically.

## Agent workflow

A fresh Codex, Claude Code, Cursor, or other capable agent opens the ResearchFlow project workspace and reads, in order:

1. `AGENTS.md` — startup and safety protocol.
2. `KNOWLEDGE.md` — compact navigation index.
3. `memory/current-state.md` — high-signal working state.
4. The relevant `skills/<name>/SKILL.md`.
5. Only the task-relevant evidence/record files, then primary sources when required.

The agent writes durable knowledge back as an Evidence, Observation, Hypothesis, Experiment, Run, or Decision record. It does not depend on a previous chat session.

## Toy E2E

`examples/toy-research/` is a deterministic `TEST / MOCK` fixture. The test suite creates a real independent Git repository and experiment worktree, commits one allowed change, runs smoke/pilot/full, collects artifacts, and verifies identical metrics. These metrics prove only pipeline reproducibility and are never scientific evidence.

```powershell
python -m pytest tests/test_e2e_toy.py -q
```

## Documentation

- [Architecture](docs/architecture.md)
- [Concepts and epistemic boundaries](docs/concepts.md)
- [Interface design](docs/interface-design.md)
- [Workflow and state machines](docs/workflow.md)
- [CLI reference](docs/cli.md)
- [Schemas](docs/schemas.md)
- [Development](docs/development.md)
- [Definition of Done audit](docs/definition-of-done-audit.md)
- [Cross-folder and new-session usage](docs/cross-folder-session-usage.md)
- [Prompt: continue an existing project](docs/prompts/continue-existing-project.md)
- [Prompt: start a new topic](docs/prompts/start-new-topic.md)
- [System-build handoff](docs/handoffs/researchflow-system-build.md)

## Current limitations

- SSH submit/status/collect/register has been validated against a real server with a deterministic `TEST / MOCK`, CPU-only fixture. This proves the remote workflow and provenance path, not GPU scheduling quality or any scientific result.
- A remote heavy run uses an atomic server-side lock directory. The protocol coordinates ResearchFlow clients, but unrelated processes can ignore it; no real GPU/heavy workload has been validated yet.
- Remote repositories must already contain the pinned commit. Datasets, checkpoints, videos, and repository contents are never auto-synchronized; remote worktrees/runs are retained and are not automatically cleaned up.
- Literature analysis remains human/agent-assisted. Zotero supplies local full-text search, attachment/annotation context, and citation formatting; ResearchFlow supplies a page-cited deep-read template plus an explicit verification/fingerprint gate, but has no built-in PDF parser, embeddings, or vector database.
- The cross-paper matrix has versioned templates/custom axes, explicit migration, completeness/evidence validation, and deterministic rendering. Its cells still require primary-source reading; scaffolded text is an agent-generated draft, not a scientific judgment.
- ID allocation is atomic on one local filesystem, not a distributed multi-writer protocol.
- There is no remote cancel command, GUI, cloud sync, scheduler daemon, or automatic merge/push.

The current acceptance boundary is the reusable ResearchFlow system, not continued expansion of one topic's paper corpus. External discovery, additional deep reads, remote cancellation, and retention automation remain separate workflows and do not block the V0.5.0 system boundary.
