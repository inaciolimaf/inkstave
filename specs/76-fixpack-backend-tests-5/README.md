# Spec 76 — Fix-pack: backend test completeness & tool-output contracts

**Type:** 🩹 fix-pack · **Phase:** validation remediation · **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec — it is a curated bundle of **confirmed issues** found by a
validation pass (two independent reviewers agreed each is real). Do this:

1. **Read the requirements.** The authoritative, per-issue requirements are in
   [`spec.md`](spec.md) next to this file. Apply **exactly** the fixes it lists —
   no more, no less.
2. **Stay inside the file set.** This fix-pack was selected so its files are
   **disjoint** from every other parallel fix-pack (parallel-safe). **Do NOT
   touch any file outside the "Files in scope" list in `spec.md`.** If a fix
   seems to need an out-of-scope file, stop and flag it rather than editing it.
3. **Mostly test-completeness, plus one small tool-output contract.** Most issues
   add missing test cases that the source specs required (HTTP 413, cross-project
   404, bounded-query N+1, CRDT convergence, DEL-char rejection). Two issues are
   small `locate_section` tool-output corrections.
4. **No unrelated refactors.** Fix only what each issue describes.
5. **Follow `CLAUDE.md`.** Match existing style and the approved stack
   (pytest + httpx, async-first).
6. **Tests stay green and fast.** Run the full suite after your changes; it must
   pass and stay **under 2 minutes**. Slow work (LaTeX, real LLM) must remain
   stubbed.

When every Acceptance criterion and Definition-of-Done item in `spec.md` passes,
this fix-pack is complete.

## One-line goal

Close confirmed backend test-coverage gaps (HTTP 413, diff/cross-project 404,
bounded-query list endpoints, cross-instance CRDT convergence, DEL-char) and the
two `locate_section` output-contract fixes — without touching any other pack's
files.

## Do NOT (scope guard)

- Do not edit files outside the "Files in scope" list in `spec.md`.
- Do not implement features that belong to later specs.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let any new test add real wall-clock waits or unstubbed slow work.
