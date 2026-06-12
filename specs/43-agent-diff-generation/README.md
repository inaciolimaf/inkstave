# Spec 43 — Agent Diff Generation (per-file unified diffs)

**Type:** 🟢 feature  ·  **Phase:** AI writing agent  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements are in
   [`spec.md`](spec.md). Implement *exactly* what it describes — no more, no less.
   Prefer the simplest option consistent with `CLAUDE.md`; ask rather than invent
   scope.
2. **Confirm prerequisites.** Depends on: **42** (the `propose_edit` tool that
   stages `StagedEdit`s into `AgentState`), which itself depends on 41/12/13.
   These must be implemented and green.
3. **Study the Overleaf reference (for understanding only).** **There is none for
   the agent** — Overleaf has no AI agent and no proposed-diff workflow. You MAY
   glance at Inkstave's **own** spec 38 (history diff viewer) for diff-rendering
   *concepts*, but write your own implementation; do not couple to it and do not
   copy Overleaf.
4. **Implement** turning staged edits into **per-file unified diffs**, the
   `proposed_diffs` persistence (with hunks and base-version tracking), and the
   drift-detection logic. **Nothing is ever applied automatically.**
5. **Write the tests** listed in the Test plan (LLM always mocked).
6. **Verify.** Full suite passes under the 2-minute budget. Check every
   Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** Add an ADR for the hunk model and base-version/drift
   strategy if non-trivial.

When all Definition-of-Done items pass, this spec is complete. Move to spec 44.

## One-line goal

Staged agent edits become **reviewable per-file unified diffs** — computed against
current document content, modeled as individual hunks, base-version-tracked for
drift, and stored in a `proposed_diffs` table — with **nothing applied
automatically**.

## Do NOT (scope guard)

- Do not **apply** diffs to documents — accepting/applying hunks is the
  endpoint+UI in spec 47.
- Do not build the **streaming API / ARQ** — spec 44 (it emits `diff_proposed`
  events referencing rows this spec creates).
- Do not build any **frontend** — diff-review UI is spec 47.
- Do not modify document content here in any way.
- Do not copy Overleaf source code (there is none for the agent).
