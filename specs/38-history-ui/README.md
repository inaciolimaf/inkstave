# Spec 38 — History UI (timeline, diff viewer, restore)

**Type:** 🟢 feature  ·  **Phase:** Phase 5 — Version history  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on **37** (history API: versions,
   diff, restore, labels) and **24** (PDF preview UI / the editor shell those
   panels live in). They must already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Use it only for layout/UX ideas; write your own React.
4. **Implement** the history view: a versions timeline (author + timestamp), a
   diff viewer with added/removed highlighting, label management, and a "restore
   this version" action with confirmation. Use shadcn/ui components.
5. **Write the tests** listed in the spec's Test plan (Vitest unit + one Playwright
   flow with the backend mocked/stubbed).
6. **Verify.** Run the full test suite. It must pass and stay under the 2-minute
   budget. Then check every Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** If you made a UI architectural decision, add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 39.

## One-line goal

From inside the editor, a user can open a History view, browse versions with
authors/timestamps, see a highlighted diff between versions (or version↔current),
manage labels, and restore a version with a confirmation step.

## Do NOT (scope guard)

- Do not change the history API (spec 37) or capture/storage (spec 36).
- Do not hand-roll a diff *algorithm* in the frontend — render the diff the API
  returns (spec 37). You only render added/removed highlighting.
- Do not copy Overleaf source code or CSS.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
