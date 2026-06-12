# Spec 13 — Document content API

**Type:** 🟢 feature  ·  **Phase:** Projects & files  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **12** (tree entities; a `doc`
   entity is what holds content) and transitively **11/02/03/04/08**.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside `../overleaf/`. **Do not
   copy or translate any Overleaf code.** Overleaf stores docs as line arrays with
   ranges in MongoDB (docstore); Inkstave stores a single text blob + integer
   version in Postgres. Learn the *versioning / save semantics*, then write your
   own implementation.
4. **Implement** the backend: model, schemas, service, router, Alembic migration.
5. **Write the tests** listed in the spec's Test plan (unit + integration).
6. **Verify.** Run the full suite (< 2 min). Check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** Add an ADR if you make a non-obvious choice.

When all Definition-of-Done items pass, this spec is complete. Move to spec 14.

## One-line goal

The text source of a `.tex`/text document can be read and replaced through a REST
API with optimistic, version-checked saves — the single-user baseline that
real-time CRDT collaboration (Phase 4) later layers on top of.

## Do NOT (scope guard)

- Do not implement real-time sync, CRDTs, WebSockets or operational transforms —
  that is Phase 4 (specs 28+).
- Do not implement frontend autosave or the editor — specs 18/19.
- Do not store binary bytes — spec 14.
- Do not implement version *history* (snapshots/diffs/restore) — Phase 5 (36+).
  The `version` integer here is an optimistic-concurrency counter, not history.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
