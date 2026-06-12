# Spec 84 — Fix-pack: docs, ADR alignment & test-coverage gaps

**Type:** 🔧 fix-pack  ·  **Phase:** validation remediation  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** for the Inkstave system. A validation pass
(two independent reviewers) confirmed the issues listed in [`spec.md`](spec.md).
Your job is to apply **exactly** those fixes — no more, no less.

This pack is **docs-focused**: most issues are documentation edits (ADR/changelog
acknowledgements, a constructor-signature note, a small interface alignment) plus
a few missing component/UI tests. Be precise about which document and what
content to add.

Rules:

1. **Read the requirements.** The authoritative list of confirmed issues and the
   concrete fix for each is in [`spec.md`](spec.md) next to this file. Apply each
   one as described.
2. **Files are disjoint from every other fix-pack (parallel-safe).** Only edit the
   files listed in `spec.md` §2 "Files in scope". Do **not** touch any file
   outside that set; other packs may be running concurrently on other files.
3. **No unrelated refactors.** Fix the listed issues only. Do not reformat,
   rename, or restructure code that is not part of a fix.
4. **Keep tests green and fast.** After applying the fixes, run the relevant test
   suites. They must pass and the full suite must stay under the 2-minute budget.
5. **Follow `CLAUDE.md`.** Match existing style, conventions, and the approved
   stack. Do not copy Overleaf code.

When every Acceptance criterion and Definition-of-Done item in `spec.md` passes,
this fix-pack is complete.

## One-line goal

Close confirmed diff-review and share-dialog test gaps and reconcile a handful of
ADR/changelog/interface deviations (token streaming, per-run cost, S3 streaming,
OutputStore signature, single-threaded test timing) with the documentation —
without regressions.

## Do NOT (scope guard)

- Do not edit files outside the "Files in scope" list in `spec.md` §2.
- Do not implement features from other specs or invent new scope.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
