# Spec 36 — History Capture from the CRDT Stream

**Type:** 🟢 feature  ·  **Phase:** Phase 5 — Version history  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **28** (pycrdt document model,
   Yjs protocol, persistence) and **13** (document content storage & CRUD). They
   must already be implemented and their tests passing. It also leans on **14**
   (binary/blob storage abstraction) for large payloads.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
   Note: Overleaf derives history from sharejs/OT operations; Inkstave derives it
   from the **CRDT (Yjs/pycrdt) update stream**. The storage/chunking *ideas*
   transfer; the source of truth does not.
4. **Implement** the backend changes described in `spec.md` (capture trigger,
   data model + migration, compaction ARQ job, blob offloading).
5. **Write the tests** listed in the spec's Test plan (unit / integration). The
   compaction job must be exercised directly but mocked where it would be
   triggered, to keep the suite fast.
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. chunk size,
   debounce window), add a short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 37.

## One-line goal

The system durably records an incremental, restorable version history for every
document by snapshotting and capturing CRDT updates, without slowing live editing.

## Do NOT (scope guard)

- Do not implement the history **API** (list/diff/restore/labels) — that is spec 37.
- Do not implement any history **UI** — that is spec 38.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
