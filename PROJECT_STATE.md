# Project State

- last_verified: 2026-08-11 Asia/Shanghai
- durable_goal: Deliver and operate a local-first personal ResearchFlow that supports multiple research topics from evidence retrieval and literature synthesis through hypotheses, experiments, runs, decisions, and cross-session continuation.
- success_criteria: A researcher can initialize or resume a topic, preserve evidence and provenance, generate evidence-linked idea candidates, execute bounded approved experiments, recover state in a new session, and protect the durable record against accidental loss without treating automation as scientific judgment.
- active_workstream: researchflow/system-delivery-and-live-use
- current_milestone: Transition from V0.4.2 engineering acceptance to bounded real-use validation and operational hardening.
- current_task: Begin one real research workflow while deciding and implementing the minimum durability hardening required before ResearchFlow becomes the sole long-term research record.
- status: in_progress

## Milestones

1. [verified] V0.4.2 core control-plane DoD: records, CLI, Git/worktree gates, run provenance, cooperative compute locks, TEST/MOCK E2E, and local-only doctor.
2. [verified] Literature workflow on embodied-nav: 18 verified papers, 12 comparison axes, 216 supported cells, 10 syntheses, and 6 evidence-linked ideas; matrix validation passes.
3. [verified] Cross-folder and new-session entry: explicit project selection plus separate continue-existing-project and start-new-topic prompts.
4. [in_progress] Use ResearchFlow in a bounded real research workflow and capture usability failures without confusing research progress with system development.
5. [planned] Add and test durable backup/restore or snapshot/export before treating the ResearchFlow home as the sole long-term record.
6. [planned] Evaluate guided topic bootstrap and explicit XIDEA-to-HYP provenance after the real-use pilot identifies actual friction.

## Verified Facts

- Repository `F:\codespace\ResearchOS` is on `main` at `565b5478465ea78dee668ea3e913e7a39cb66235`; the worktree was clean before this ledger was created.
- The package reports V0.4.2 behavior and the full local suite passes 43 tests on 2026-08-11.
- `rf --project embodied-nav doctor` passes local integrity checks and skips the configured SSH machine unless a live probe is explicitly requested.
- The embodied-nav literature matrix validates with 18 papers, 12 axes, 216 supported cells, 10 syntheses, and 6 ideas.
- Zotero Local API is currently unreachable because Zotero Desktop/local API is not running; `rf evidence zotero status` exits 2 with an actionable message.
- `C:\Users\Modes\ResearchFlow` and the embodied-nav ResearchFlow workspace are not Git repositories. No built-in backup, restore, snapshot, or export command is present in the current CLI/code/docs.
- Cross-paper ideas are schema-validated as `XIDEA-*`, but the Hypothesis schema directly references only `OBS-*` and `PAPER-*`; explicit idea-promotion provenance is not yet represented.
- The embodied-nav research project currently has no active ResearchFlow Hypothesis or Experiment. Its independent code repository is recorded as dirty, and remote execution would require recreating an approved pinned controlled clone.

## Decisions

- ResearchFlow is deliverable now as a personal, local, human-in-the-loop research MVP. This does not imply autonomous scientific judgment or production-grade durability.
- Additional embodied-nav paper accumulation is research use, not a prerequisite for closing the system engineering DoD.
- Real GPU/heavy, robot, remote cleanup, Zotero write, merge, and push remain explicit human-authority actions.

## Risks And Unknowns

- The durable ResearchFlow home has no verified backup/restore path; local file readability alone does not protect against disk loss or accidental deletion.
- Live scholarly discovery is performed by the agent/web tools and Zotero rather than recorded as a first-class reproducible ResearchFlow search batch.
- Paper-level and cross-paper ideas are evidence-linked, but promotion into a Hypothesis loses the direct `IDEA/XIDEA` identifier.
- The full zero-to-real-experiment user journey has not yet been validated as one bounded live-use pilot; toy E2E verifies plumbing, not scientific usability.
- Real remote GPU/heavy execution remains unvalidated under the current controlled-clone state.

## Next Step And User Decision

- Next concrete action: choose whether to start the first bounded live-use workflow immediately with an external/manual backup, or first implement a tested ResearchFlow backup/restore command. No external or research execution action is authorized by this ledger.
- User decision: whether long-term durability hardening must precede the first live research workflow.
