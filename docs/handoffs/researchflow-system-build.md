# ResearchFlow system-build handoff

## Handoff identity

- Workstream: `researchflow/system-build`
- Repository: `F:\codespace\ResearchOS`
- ResearchFlow home: `C:\Users\Modes\ResearchFlow`
- Target release: `0.4.2`
- Created: `2026-08-11 Asia/Shanghai`
- Scope: ResearchFlow control-plane implementation and acceptance, not embodied-navigation research execution

## Goal and acceptance contract

Maintain a local-first research control plane that persists Evidence, Observation, Hypothesis, Experiment, Run, Decision, provenance, current state, and literature analysis across directories, chat sessions, and machines. The accepted A-I contract is recorded in `docs/definition-of-done-audit.md`.

## Current verified state

- The public CLI, filesystem records, project startup files, Git/worktree safety, deterministic TEST/MOCK E2E, single-GPU cooperative locking, Zotero read-only boundary, verified deep-read records, and structured cross-paper matrix are implemented.
- `rf doctor` is local-only by default. `--probe-machines` is required for live local/SSH probes.
- `project show ID` prints the resolved workspace and startup files.
- An explicit `rf --project ID ...` invocation works independently of the current directory.
- Two canonical new-chat entry prompts distinguish continuing an existing project from initializing a new topic.
- Zotero owns bibliography/PDFs; ResearchFlow owns project-specific analysis and evidence relationships.

## Files to read first

1. `F:\codespace\ResearchOS\AGENTS.md`
2. `F:\codespace\ResearchOS\KNOWLEDGE.md`
3. `F:\codespace\ResearchOS\docs\definition-of-done-audit.md`
4. `F:\codespace\ResearchOS\docs\cross-folder-session-usage.md`
5. `F:\codespace\ResearchOS\docs\prompts\continue-existing-project.md` or `docs\prompts\start-new-topic.md`, according to the requested mode
6. The selected project's `AGENTS.md`, `KNOWLEDGE.md`, and `memory/current-state.md` printed by `rf project show ID`

## Boundaries and unresolved optional work

- Do not infer a scientific result from TEST/MOCK system tests.
- Do not contact remote machines, run GPU/robot workloads, clean assets, write Zotero, or push Git without current authorization.
- Real GPU/heavy validation, remote cancel/retention automation, GUI/cloud sync, and additional literature discovery are optional future work.
- `default_project` is convenience only; explicit `--project` is the safe cross-topic interface.

## Recovery commands

```powershell
Set-Location F:\codespace\ResearchOS
$env:PYTHONUTF8 = '1'
git rev-parse --show-toplevel
git status --short
& .\.venv\Scripts\rf.exe project list
& .\.venv\Scripts\rf.exe project show embodied-nav
& .\.venv\Scripts\rf.exe --project embodied-nav status
& .\.venv\Scripts\rf.exe --project embodied-nav doctor
```

The last command is local-only unless `--probe-machines` is explicitly added.

## Copyable prompt for a new chat

```text
继续 F:\codespace\ResearchOS 的 ResearchFlow system-build 工作流，不要依赖旧对话记忆。
先读取仓库 AGENTS.md、KNOWLEDGE.md、docs/definition-of-done-audit.md、
docs/cross-folder-session-usage.md、docs/prompts/continue-existing-project.md
和 docs/handoffs/researchflow-system-build.md。
先运行 git rev-parse --show-toplevel、git status --short，核验当前提交和未提交改动。
若任务针对 embodied-nav，再运行：
F:\codespace\ResearchOS\.venv\Scripts\rf.exe project show embodied-nav
并读取输出的三个项目启动文件，然后运行：
F:\codespace\ResearchOS\.venv\Scripts\rf.exe --project embodied-nav status
先报告核验事实、边界和一项优先建议；未经本轮明确授权，不进行 SSH/GPU/机器人、清理、Zotero 写入或 Git push。
```
