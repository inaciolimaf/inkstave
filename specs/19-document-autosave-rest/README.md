# Spec 19 — Document Autosave (REST)

**Type:** 🟢 feature  ·  **Phase:** Projects & files  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **18** (the CodeMirror 6
   editor pane and IDE shell) and **13** (document content API, including the
   version-checked replace-content endpoint with optimistic concurrency). They
   must already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own.
4. **Implement** editable mode + debounced REST autosave described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan.
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision, add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 20.

## One-line goal

A single user can edit a document and have changes auto-saved to the server over
REST, with a clear saved/dirty indicator and version-conflict handling — the
pre-realtime baseline that CRDT (Phase 4) will later replace/augment.

## Do NOT (scope guard)

- Do not implement multi-user realtime collaboration, Yjs/CRDT or WebSocket
  sync (specs 28+). This is deliberately single-user REST autosave.
- Do not implement compile/preview, history snapshots, or AI features.
- Do not copy Overleaf source code (including document-updater logic).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
