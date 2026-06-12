<!--
  CANONICAL TEMPLATE for a spec folder's README.md.
  This README is the PROMPT handed to the agent that implements the spec.
  Keep it short and directive; the heavy detail lives in spec.md.
  Replace every <PLACEHOLDER>. Delete these HTML comments in real specs.
-->

# Spec NN — <Human Title>

**Type:** 🟢 feature  ·  **Phase:** <phase name>  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: <list previous spec numbers,
   e.g. "01, 02, 03">. They must already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
4. **Implement** the backend and/or frontend changes described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit / integration / e2e).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision, add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec NN+1.

## One-line goal

<One sentence describing what the system can do after this spec that it couldn't before.>

## Do NOT (scope guard)

- Do not implement features that belong to later specs (see `specs/README.md`).
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
