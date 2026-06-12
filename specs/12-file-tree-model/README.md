# Spec 12 — File tree model (folders / docs / files)

**Type:** 🟢 feature  ·  **Phase:** Projects & files  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **11** (project entity &
   ownership). It also relies on **02/03/04/08** as 11 did.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside `../overleaf/`. **Do not
   copy or translate any Overleaf code.** Overleaf nests folders/docs/files inside
   the Project document and resolves paths by walking that tree; Inkstave uses a
   flat relational table with a self-referencing parent. Learn the *path-safety
   and tree-operation rules*, then write your own implementation.
4. **Implement** the backend: model, schemas, service, router, Alembic migration.
5. **Write the tests** listed in the spec's Test plan (unit + integration).
6. **Verify.** Run the full suite (< 2 min). Check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** Add a short ADR for the chosen tree representation.

When all Definition-of-Done items pass, this spec is complete. Move to spec 13.

## One-line goal

A project owner can build and reorganise a project's file tree — create folders,
documents and file placeholders; rename, move (reparent) and delete them; and
list the whole tree — with strict path-safety and per-folder unique names.

## Do NOT (scope guard)

- Do not store document **text content** — that is spec 13 (this spec only
  creates the doc *entity*/row in the tree).
- Do not store binary **bytes** — that is spec 14 (this spec only creates the
  file *entity*/row and a place to reference blob storage).
- Do not build the tree UI or drag-and-drop — that is spec 17.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
