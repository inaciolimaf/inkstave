# Spec 47 — Diff Review UI

**Type:** 🟢 feature  ·  **Phase:** AI writing agent  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **46** (the chat panel that
   surfaces proposed-diff entry points), **43** (per-file unified diff
   generation — the diff format and proposal model), and **18** (the editor /
   CodeMirror surface and the document it writes back into via the CRDT
   binding). They must already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** For diff
   *layout/UX ideas only*, you may look at
   `services/web/frontend/js/features/history/` diff rendering. The agent itself
   has **no Overleaf equivalent**. Learn the visual approach, then write your
   own. **Do not copy or translate any Overleaf code** (AGPLv3).
4. **Implement** the diff review experience described in `spec.md` (frontend,
   plus a thin apply path that writes accepted hunks as a CRDT update).
5. **Write the tests** listed in the spec's Test plan (Vitest + RTL units on
   deterministic diffs; one minimal Playwright e2e using a FakeLLM-backed
   proposal).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision, add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 48.

## One-line goal

A user reviews the agent's proposed per-file unified diffs, accepts or rejects
them hunk-by-hunk and file-by-file, previews the result, and on Apply writes only
the accepted hunks into the live CRDT document so collaborators see the change —
with nothing applied without explicit confirmation and a clear warning if the
base changed.

## Do NOT (scope guard)

- Do not generate diffs or run the agent — diffs come from spec 43 via spec 44;
  this spec only *reviews and applies* an existing proposal.
- Do not build the chat panel (spec 46) or the LaTeX context parser (spec 48).
- Do not implement rate limits / cost budgets / audit logging / evals (spec 49).
- Do not auto-apply anything; every apply requires explicit user confirmation.
- Do not copy Overleaf code — history diff rendering is for UX *ideas only*.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not hand-roll diff/scroll/modal CSS; prefer shadcn/ui + CodeMirror.
