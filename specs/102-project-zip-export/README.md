# Spec 102 — Project ZIP Export (download whole project as .zip)

**Type:** 🟢 feature  ·  **Phase:** import/export  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **11** (project model/CRUD),
   **12** (file-tree model + `tree_service`), **13** (document content), **14**
   (binary file storage + `ObjectStore`), **28/31** (CRDT content + content
   bridge / flush), **34** (capability-based authorization). They must already
   be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/` (verified to exist:
   `services/web/app/src/Features/Downloads/ProjectZipStreamManager.mjs` and
   `ProjectDownloadsController.mjs`). **Do not copy or translate any Overleaf
   code** — it is AGPLv3 and Inkstave is MIT. Learn the streaming-zip approach,
   then write your own implementation.
4. **Implement** the backend endpoint + zip-builder service and the frontend
   "Download as .zip" action described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit / integration / e2e).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. the
   sync-stream vs. ARQ-artifact threshold), add a short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec NN+1.

## One-line goal

A project member can download the entire project — every folder, text document
(current CRDT-flushed content) and binary file, with the tree preserved — as a
single streamed `.zip`.

## Do NOT (scope guard)

- Do not implement project *import* (the round-trip counterpart) here. Project import is specified in **spec 101**; only add the round-trip *test*
  once the import path is implemented — otherwise mark it skipped (see `spec.md` §8).
- Do not buffer the whole archive in memory; the archive must stream.
- Do not implement features that belong to later specs (see `specs/README.md`).
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
