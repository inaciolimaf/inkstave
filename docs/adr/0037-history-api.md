# ADR 0037 — History API: restore-as-edit, text extraction, project labels

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 37 — History API (list, diff, restore, labels)

## Context

Spec 36 captures a per-document version history (chunks + updates +
`reconstruct_state`). Spec 37 exposes it over REST: list versions/updates, diff,
restore (non-destructive), and labels. The interesting decisions are how a restore
interoperates with the live pycrdt room and how text is extracted consistently.

## Decisions

### 1. Restore is a *new edit*, not a destructive overwrite

`POST …/docs/{id}/history/restore` reconstructs the target version's **text** via
spec-36 `reconstruct_state`, then applies it to the authoritative pycrdt document
through a new manager hook **`DocumentManager.apply_server_update(doc_id, new_text,
origin)`** — which acquires the doc (loading it if no clients are connected),
`replace_text`s the shared `Y.Text` in one transaction, persists the resulting CRDT
update, and returns it. The restore service then **broadcasts** that update over the
spec-29 Redis path (so open editors converge) and **captures** it via spec 36 as a
brand-new version authored by the restoring user. No `history_*` row is ever
deleted or rewritten; restoring v90 onto a doc at v142 yields v143.

This works because history and the live doc share the **same CRDT lineage** (history
captures the manager's own updates), so a `replace_text` update computed on the live
doc, when captured and replayed, reconstructs exactly the target text.

### 2. Atomicity / "live room unreachable" → 409

If `apply_server_update` cannot mutate the authoritative doc (no collab components,
or the mutation raises), the restore fails with **409** *before* any broadcast,
capture, or label write — nothing changes. The persisted CRDT update only happens
inside `apply_server_update`, which either fully succeeds or raises.

### 3. One text-extraction contract

`history/reconstruct.py` centralises `reconstruct_state`/`reconstruct_doc` (replay a
chunk's updates onto its base), `text_from_state` (the shared `Y.Text` named
`content`), `load_current_state`/`current_text` (the live authoritative state from
the spec-28 store), and `is_binary`. Spec-36 capture now delegates to the same
module, so capture, diff and restore agree byte-for-byte. **Binary** detection is a
NUL-byte check on the extracted text → `{"binary": true, "hunks": []}`.

### 4. Diff: line-level, difflib-based, round-trippable

`history/diff.py` uses Python's `difflib.SequenceMatcher.get_grouped_opcodes` to
emit unified hunks of `context | added | removed` **line** segments (word-level
refinement is left to the spec-38 renderer). `apply_hunks(a, hunks) == b` is a
tested invariant (criterion 3). `to=current` diffs against the live document; a
side larger than `HISTORY_DIFF_MAX_BYTES` returns **413** `{too_large: true}` with
no diff work; the versions listing tolerates compaction gaps (only versions that
still have an update row appear) and paginates by `before`/`limit`.

### 5. Project-level labels carry a `{doc_id: version}` marker

`history_labels` gains a `payload jsonb` column. A **project-level** label
(`doc_id IS NULL`) snapshots every document's current history version at creation
time into `payload`; `POST …/history/restore` reads that map and restores each doc
to its marked version, reporting per-doc `restored`/`skipped`/`error` and **never
rolling back** an already-restored doc on a later failure. Partial unique indexes
(`WHERE doc_id IS NOT NULL` / `WHERE doc_id IS NULL`) keep names unique within their
scope.

### 6. Authorization

All routes go through the spec-34 guard: list/diff/labels-list need `PROJECT_READ`
(any member); restore and label create/delete need `DOC_WRITE` (editor/owner).
Non-members get **404** (no existence leak); members lacking the capability get
**403**. The endpoint also verifies the `doc_id` belongs to the project (else 404),
closing a cross-project history-read hole.

## Consequences

- New `history_labels` table + migration `d4e6a8b02c35`. New `history/`
  modules (`reconstruct`, `diff`, `read`, `labels`, `restore`) and
  `api/routes/history.py`. New `DocumentManager.apply_server_update` /
  `current_text`. Two new settings (`HISTORY_DIFF_MAX_BYTES`,
  `HISTORY_VERSIONS_PAGE_MAX`). Capture (spec 36) refactored to share the
  reconstruct module (no behaviour change; its tests stay green).
- Restore tests drive the spec-28 service layer in-process and mock the broadcast
  transport (asserting `redis_bridge.publish` was invoked) — no real WebSocket.
