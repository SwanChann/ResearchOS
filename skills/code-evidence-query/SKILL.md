---
name: code-evidence-query
description: Verify implementation claims against an actual repository at a pinned commit.
---

# Code Evidence Query

Use for architecture, loss, preprocessing, defaults, scaling, training, or evaluation behavior.

1. Resolve a `REPO-*` manifest and require `pin.commit`.
2. Confirm the local/official repository contains that commit; inspect the exact source and configuration paths.
3. Cross-check paper wording only when it helps distinguish intended method from implementation.
4. Return Verified Code findings with REPO ID, commit, paths/symbols, uncertainty, and any paper/code mismatch.

Do not answer from README prose alone when source exists. Do not silently inspect a different branch or latest commit.
