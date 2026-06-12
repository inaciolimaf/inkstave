# Spec 17 — File Tree UI

**Type:** 🟢 feature  ·  **Phase:** Projects & files  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **16** (project dashboard UI
   and the `/projects/:projectId` editor route shell) and **12** (file-tree
   model API: folders/docs/files, paths, moves). They must already be
   implemented and their tests passing. Binary upload uses the **14** API.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own.
4. **Implement** the frontend file-tree panel described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (Vitest + RTL units; one
   Playwright e2e flow).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision, add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 18.

## One-line goal

Inside a project, the user sees a navigable file tree and can create, rename,
move (drag-and-drop), delete files/folders and upload binary files.

## Do NOT (scope guard)

- Do not implement the CodeMirror editor pane or document content loading
  (spec 18) — selecting a doc here only emits a selection event/route param.
- Do not implement autosave (19), compile/preview, or collaboration cursors.
- Do not build a binary file *viewer* (image/PDF preview in the editor) — that
  belongs to later specs; uploaded binaries appear in the tree only.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Prefer ready-made shadcn/ui components for menus, dialogs and inputs.
