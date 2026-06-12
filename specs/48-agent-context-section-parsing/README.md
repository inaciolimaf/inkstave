# Spec 48 — Agent Context & LaTeX Section Parsing

**Type:** 🟢 feature  ·  **Phase:** AI writing agent  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **42** (the agent tools,
   including `locate_section`, which this spec sharpens) and **18** (the editor /
   document model the parser reads from). They must already be implemented and
   their tests passing. Specs 41–44 (agent core) are assumed present.
3. **Study the Overleaf reference (for understanding only).** You may look at
   `services/web/frontend/js/features/source-editor/lezer-latex/` to understand
   *conceptually* how LaTeX structure is parsed. **You must NOT copy or translate
   the lezer-latex grammar** (AGPLv3) — LaTeX structure is public; write your own
   lightweight structural parser. The agent feature itself has **no Overleaf
   equivalent**.
4. **Implement** the LaTeX structure parser, the project context/map builder,
   and context-window management described in `spec.md` (backend, integrated into
   the spec-42 tools).
5. **Write the tests** listed in the spec's Test plan (pytest units on the
   parser + context builder; FakeLLM where the agent is involved).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision, add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 49.

## One-line goal

The agent gains precise project awareness: a LaTeX-structure parser that maps
sections/subsections/environments to file+line ranges, a project map the agent's
tools use to ground themselves, and context-window management that selects the
relevant chunks — so "edit the introduction" resolves to the right place.

## Do NOT (scope guard)

- Do not copy Overleaf's lezer-latex grammar or any Overleaf code. Write your own
  structural parser; you are not building a full LaTeX compiler/AST.
- Do not build the chat panel (46), the diff review/apply (47), or safety/evals
  (49).
- Do not change diff generation (43) or the streaming protocol (44) beyond
  feeding them better context.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
