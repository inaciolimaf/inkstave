# Spec 14 — Binary file storage (uploads & storage abstraction)

**Type:** 🟢 feature  ·  **Phase:** Projects & files  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **12** (`file` tree entities)
   and transitively **11/02/03/04/08**. It also pairs with **13** patterns
   (satellite row keyed to a tree entity).
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside `../overleaf/`. **Do not
   copy or translate any Overleaf code.** Learn the *storage-abstraction shape*
   (put/get/delete/stat, streaming, local↔S3 backends, 404 fallback), then write
   your own implementation.
4. **Implement** the backend: storage interface + two backends, model, schemas,
   service, upload/download router, Alembic migration.
5. **Write the tests** listed in the spec's Test plan (unit + integration). The S3
   backend is exercised against a **mocked/faked** S3 (no network) to keep the
   suite fast.
6. **Verify.** Run the full suite (< 2 min). Check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** Add an ADR for the storage key scheme.

When all Definition-of-Done items pass, this spec is complete. Move to spec 15.

## One-line goal

A project owner can upload binary files (images, PDFs, `.bib`, etc.), which are
stored through a pluggable storage backend (local filesystem by default, optional
S3-compatible) and linked to `file` entities in the project tree, then streamed
back on demand with auth.

## Do NOT (scope guard)

- Do not serve files into LaTeX compiles — the compile specs (21–23) fetch bytes
  via the storage interface this spec provides.
- Do not implement the upload UI / drag-and-drop — spec 17.
- Do not store document **text** — spec 13.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
