# Project State

- last_verified: 2026-08-12 Asia/Shanghai
- durable_goal: Deliver and operate a local-first personal ResearchFlow that supports multiple research topics from evidence retrieval and literature synthesis through hypotheses, experiments, runs, decisions, cross-session continuation, and tested recovery.
- success_criteria: A researcher can initialize or resume a topic, preserve evidence/provenance, distinguish verification and human review from scientific claims, execute bounded approved experiments, rebuild navigation, and recover durable records without requiring a cloud service.
- active_workstream: researchflow/system-durability-and-contract-hardening
- current_milestone: V0.5.0 durability, cross-domain contracts, review/provenance, diagnostics, and the first real-workspace recovery drill have passed pre-commit review.
- current_task: The complete V0.5.0 diff was reviewed, review findings were fixed and regression-tested, and this ledger is included in the authorized local checkpoint.
- status: verified

## Milestones

1. [verified] V0.4.2 core control-plane: records, CLI, Git/worktree gates, run provenance, cooperative compute locks, TEST/MOCK E2E, and explicit live-probe boundary.
2. [verified] V0.5.0 snapshot lifecycle: atomic create, hashed manifest, list/show/verify, dry-run/new-target restore, traversal protection, confirmed in-place restore, rollback copy, custom output, redacted config option, and external-authority boundaries.
3. [verified] Structured Git diagnostics: path/repo/HEAD or unborn/branch or detached/commit/clean/tracked/untracked/checkpoint across project show/status/doctor, with WARN-compatible default and strict mode.
4. [verified] Cross-domain literature matrix: generic and embodied-navigation templates, confirmed custom axes, first-paper lock, explicit mapping migration, snapshot-backed write, superseded cell/evidence retention, legacy read, and idempotent replay.
5. [verified] Artifact registry and KNOWLEDGE generated navigation: project-scoped hashes/lineage/supersession, dry-run migration, human-region preservation, idempotent rebuild, stale/broken checks, concise/verbose status, and doctor integration.
6. [verified] Verification/review/scaffold contracts: contract/source/fingerprint/human review/reproduction/scientific-claim separation, fingerprint-bound stale review, four draft scaffolds, preflight, atomic formal writes, and snapshot-backed verification migration.
7. [verified] XIDEA provenance: formal Idea references in Hypothesis, recursive PAPER/claim evidence, novelty warning propagation, literature-derived/local-support boundary, and stale Idea/matrix detection.
8. [verified] Zotero diagnostics: invalid URL/library, loopback availability, Local API denial, library/item errors, attachment-vs-parent confusion, Server ID change, and attachment-path existence using mock GET-only servers.
9. [verified] Documentation and acceptance: README/CLI/architecture/concepts/schemas/workflow/session docs/Zotero docs/ADRs/skills/prompts updated; package version is 0.5.0; pre-commit adversarial review findings are resolved.
10. [verified] First real-workspace recovery drill: `embodied-nav` snapshot created on independent physical disk E, verified, dry-run checked, and restored exactly to a new directory without modifying the source workspace.

## Verified Facts

- Repository: `F:\codespace\ResearchOS`; branch `main`; pre-change baseline HEAD `fe6f9589b92c2a1f9493c24f372c5fbeb034ce5f`. The reviewed V0.5.0 implementation is recorded by the local commit containing this ledger; no push or merge is implied.
- Fresh pre-change baseline was 43/43 tests. Final fresh collection is 81 tests; all 81 pass. The combined new-feature focused suite passes 47 tests, and `compileall` passes.
- CLI help smoke for root, snapshot, matrix, Artifact, Knowledge, and Zotero doctor passes 6/6. `git diff --check` passes; Windows reports expected LF→CRLF checkout warnings but no whitespace errors.
- `embodied-nav` and `mllm_overthinking` each pass read-only `project show`, `status`, ordinary `doctor`, and legacy `matrix validate` (8/8 commands, no live probe). Their schema-v1 matrices remain readable and valid.
- The earlier read-only compatibility pass found no default snapshot and no V0.5.0 generated KNOWLEDGE region in either real project. Those were WARN states, not silent upgrades. The later authorized `embodied-nav` custom-directory snapshot drill did not run a Knowledge rebuild, Artifact registration, paper verification migration, or axes migration.
- The authorized `embodied-nav` recovery drill created `E:\ResearchFlowBackups\embodied-nav-20260812T114927+0000-4132e021.rfsnapshot` (archive SHA-256 `a3ddcfb6447a1d13465cbad4dfef2111ac61d950c19715083146682a492c6fe8`). Snapshot verification is valid; its manifest contains 75 workspace-record files and 735,679 bytes, with 980 temporary/large files explicitly excluded and external assets marked not backed up.
- Dry-run left the target absent, then new-target restore created `E:\ResearchFlowRestoreTests\embodied-nav`. The restored tree matches the manifest exactly: 75/75 files, equal bytes, no missing/extra/size/hash mismatches, matching project ID, and UTF-8-readable `AGENTS.md`, `KNOWLEDGE.md`, and `memory/current-state.md`.
- The real `embodied-nav` workspace stayed unchanged across the drill: 1,055 files, 960,609,869 bytes, and aggregate tree SHA-256 `b6a7ea73597eeb8c88a74bd3d4b4dae8148574a6154699fcbb1915fb4c0dee84` before and after. C is Disk 0 and E is Disk 1; the archive and restore copy therefore exercise a separate-physical-disk recovery path.
- Pre-commit review fixed project-mixing in shared snapshot directories, project-identity enforcement in snapshot verification, unsafe nested restore targets, malformed-manifest acceptance, restore-time payload revalidation, Artifact path escape and lineage cycles, ambiguous Knowledge generated markers, and missing-Git diagnostic crashes. Regression tests cover each boundary; the retained real snapshot remains valid under the hardened verifier.
- `embodied-nav` independent repo is currently dirty at `37b709be7403c78fdda8fca620ec61d0e2d53bd6` on `agent/ubuntu-sim-handoff` with 9 tracked modifications and 20 untracked files. `mllm_overthinking` is an unborn `main` repo with 8 untracked files and no recoverable Git checkpoint. These are read-only current facts and were not changed.
- Fixture/mock results validate software contracts and failure handling only. They do not establish any paper interpretation, method reproduction, model effect, GPU behavior, or scientific result.

## Decisions

- Local project files remain authoritative. Git history, workspace snapshots, private remotes, Zotero backup, and large-asset backup are separate durability layers.
- New matrices default to a generic cross-domain template. Domain/custom axes require an explicit user selection/confirmation and cannot be silently reinterpreted after data entry.
- `status: verified` remains readable for compatibility, but current output separates contract/source/fingerprint/human-review/reproduction/scientific-claim meanings.
- Real-project migrations are not implied by compatibility tests or dry-run capability and require separate user authorization.
- No automatic commit, push, GitHub setup, Zotero write, download, SSH/GPU probe, asset cleanup, or research-topic mutation is part of this completion.

## Risks And Unknowns

- Snapshot/restore is now verified on temporary fixtures and the real `embodied-nav` workspace. `mllm_overthinking` still has no independently stored snapshot or recovery drill.
- Existing real projects have legacy matrices and manually maintained KNOWLEDGE files. V0.5.0 correctly reports their generated navigation as missing/stale, but actual rebuild or schema migration remains unverified and unauthorized.
- Zotero failure classification is mock-tested. No real Zotero Desktop diagnostic was run in this task, and the UI guidance was not refreshed through external web retrieval because external search was outside authorization.
- A project snapshot does not protect the independent repo, Zotero database/PDFs, datasets, weights, or large experiment assets. Complete recovery still requires a multi-authority backup plan and restore drill.
- The V0.5.0 checkpoint is local only. No private remote/off-machine Git copy was created, so the commit protects history and rollback but not loss of the machine or repository disk.

## Next Step And User Decision

- Unique priority: stop ResearchOS system hardening at this reviewed local V0.5.0 checkpoint and return to the selected research-project workstream. This checkpoint does not authorize project migrations, SSH/GPU work, Zotero writes, merge, or push.
