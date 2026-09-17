# Definition of Done: ResearchFlow 0.8.1

- [x] Method-family matching excludes `compared_with`, `improves_over`, `extends`, and other non-adoption Method endpoints from structural, semantic, and packet profiles.
- [x] `exposes_failure` transfers directly to the same canonical Method; broader-family transfer also requires shared FailureCondition, Task, or Assumption context.
- [x] Concept resolution, Paper fingerprints, and adjacency-currentness inputs are reused within one build/check operation.
- [x] Benchmark evaluation fails closed when a negative label conflicts with a deterministic relation entailed by the accepted ontology.
- [x] Focused and full test suites pass on the final working tree (116 tests).
- [x] `compileall`, 34 JSON Schema validations, CLI help traversal, project-state validation, and `git diff --check` pass.
- [x] ResearchOS `PROJECT_STATE.md` reflects the real `CORPUS-0008` adoption and the completed Phase A boundary.

This release does not modify `embodied-nav`, accept any Paper adjacency, approve `GAP-0005`, or authorize Phase B.
