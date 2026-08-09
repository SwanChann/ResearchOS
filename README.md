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

The five commands to remember are:

```text
rf status       current question, HYP/EXP/RUN state, next action
rf evidence     paper and pinned-code evidence
rf experiment   card, worktree, preflight, bounded execution
rf run          provenance, logs, metrics, artifacts
rf doctor       config, schemas, tools, paths, references, IDs, machines
```

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
  experiments/{cards/,registry.jsonl,reports/}
  runs/{registry.jsonl,RUN-*/}
  notes/daily/
```

No database is authoritative. Datasets and large checkpoints stay in their configured local/remote locations; run records contain references and hashes where practical.

## Human workflow: problem to decision

The following is a realistic shape, not a claim that any navigation result exists:

```powershell
rf evidence paper add .\papers\method.pdf --title "Method" --year 2026 --tags navigation,diffusion
rf evidence repo add --name OfficialCode --url https://example.invalid/repo --commit abc123 --papers PAPER-0001

rf memory observation add --title "Delayed right turns" --text "Observed on the registered route review." --evidence RUN-000001
rf hypothesis new --title "Temporal context" --statement "Bounded context may reduce the delay." --observations OBS-0001 --papers PAPER-0001 --falsification "Pilot fails the turning metric or violates a guardrail."

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

## Current limitations

- SSH machine probing and remote execution plans exist, but no real server/GPU was used in validation. The coordinator lock does not yet protect against unrelated tools or another client that ignores ResearchFlow.
- Remote submit/collect/register execution is not enabled; V0.1 executes runs locally and keeps SSH plans side-effect free.
- Literature analysis is deliberately manual/agent-assisted; no PDF parser, citation engine, embeddings, or vector database is included.
- ID allocation is atomic on one local filesystem, not a distributed multi-writer protocol.
- There is no GUI, cloud sync, scheduler daemon, or automatic merge/push.

The recommended next milestone is a fake-SSH integration harness plus a server-side atomic GPU lock and small-artifact collect/register protocol. It closes the largest unverified safety/provenance gap without adding a GUI or database.
