# Spec 16 — Project Dashboard UI

**Type:** 🟢 feature  ·  **Phase:** Projects & files  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **09** (frontend foundation:
   Vite/React/TS/Tailwind/shadcn, routing, API client, auth pages) and **11**
   (project model & CRUD API). They must already be implemented and their tests
   passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the UI/UX approach, then write your own.
4. **Implement** the frontend changes described in `spec.md` (this is a
   frontend-only spec; it consumes the existing spec 11 API).
5. **Write the tests** listed in the spec's Test plan (Vitest + React Testing
   Library units; one Playwright e2e flow).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision, add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 17.

## One-line goal

A logged-in user lands on a dashboard that lists their projects and can create,
rename, delete and open a project entirely from the UI.

## Do NOT (scope guard)

- Do not implement the in-editor file tree (spec 17), the editor (18) or
  autosave (19). "Open project" only needs to navigate to the editor route shell.
- Do not implement sharing, collaborators, tags/folders, archiving or trash
  (later phases) unless spec 11 already exposes them; this spec covers owner CRUD
  only.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not hand-roll modal/table/menu CSS; prefer ready-made shadcn/ui components.
