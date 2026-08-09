# Development

## Environment

Use a project-local environment; do not install into the system interpreter.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
.venv\Scripts\rf --help
```

Runtime dependencies are intentionally limited to PyYAML (safe, readable YAML records) and jsonschema (explicit machine contracts and user-facing validation errors). The CLI, Git/SSH boundaries, locking, JSONL, subprocess runner, and filesystem operations use the standard library.

## Phase discipline

Each material phase is implemented, tested, diff-checked, simplified, documented, and committed separately. Tests use temporary homes/repositories and mark all generated metrics as `TEST / MOCK`. No test needs a GPU, network connection, or real research project.

Run focused tests while editing, then `python -m pytest`. Use `git diff --check` and inspect `git status --short` before committing. The E2E contract is `tests/test_e2e_toy.py`.
