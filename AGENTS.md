# ResearchFlow Agent Instructions

ResearchFlow is a local-first control plane. Do not place research code, secrets, datasets, or large checkpoints inside a ResearchFlow project workspace.

Before changing this repository:

1. Read `README.md`, `docs/interface-design.md`, and relevant architecture decisions.
2. Inspect Git status and preserve unrelated user changes.
3. Treat model memory as a search aid, never as research evidence.
4. Keep YAML/Markdown/JSONL human-readable and backward-compatible when practical.
5. Mark fixtures and synthetic results as `TEST` or `MOCK`; never register them as scientific evidence.
6. Run focused tests, then the full suite. Do not claim unexecuted checks passed.
7. Never run a real GPU, robot, destructive cleanup, push, or remote operation without current authorization.

