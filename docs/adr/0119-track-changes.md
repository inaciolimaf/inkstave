# ADR 0119 — Suggestions are records in the document's Yjs map, written with the text

**Status:** accepted · **Spec:** 119

## Decision

Suggesting mode records a member's edits as **suggestions** in a second shared type of the document's
`Y.Doc`, `Y.Map("suggestions")`, keyed by a UUIDv7. An insertion is `{kind: "insert", …, start, end}`, with two
relative positions (base64, the start with assoc 0, the end with assoc -1). A deletion is
`{kind: "delete", …, at, text}`, with the removed text and one relative position. The text itself is the
suggested version: it holds the inserted text, and a deletion is gone from it. Accept and reject are Yjs
transactions with the origin `review-decision`.

The text change and its record are written in **one Yjs transaction**, with the sync origin of the editor,
so `Y.UndoManager([ytext, suggestions])` reverts both with one undo.

The server stores and relays the whole `Y.Doc` as it did before, so the map persists through the snapshots and
the log with no server code. The server reads it only in a test. `documents.content` is still written from
`Y.Text("content")` alone, so compile, the agent and the export see the suggested text and no record.

## Spike: the CodeMirror to Yjs path (spec 119 §5.3)

The question was whether `y-codemirror.next` 0.3.5 can write the text and the map in one transaction.

- Its sync plugin (`ySync`) writes the text in its own `ytext.doc.transact(…, this.conf)` inside its
  `update()`. The transaction is internal: the plugin takes no hook where another change can join it, and
  the nested `transact` only joins a transaction that is already open, which this one is not.
- The library's undo manager tracks the library's origin object, so the map change would not be undone with
  the text unless it used that origin too.

**Result: not possible without replacing the sync plugin.** The chosen path is an Inkstave sync plugin,
`frontend/src/modules/collab/suggestions/suggest-extension.ts`. It takes the place of `ySync` only, which is
filtered out of the `yCollab(...)` array. It keeps the library's pieces: the undo manager plugin and its
keymap, the `ySyncFacet` configuration (the origin the undo manager tracks), and the remote cursors
(`yRemoteSelections`). It does what `ySync` did for remote text, and for local edits it plans the records and
writes them, with the text, in one `transact`. The test `one undo reverts a suggested deletion` covers the
single-undo behaviour with the library's undo manager.

The library's `ySyncAnnotation` is not exported and its package `exports` map blocks deep imports, so the
plugin marks its remote dispatches with its own annotation. The library's undo manager reads the annotation
only to skip storing the selection for remote changes, so the difference is limited to that selection.

## Why

- **Overleaf** tracks changes as offset ranges that its document service shifts on each operation
  (`RangesManager`), and stores deleted text with the change. Inkstave already has a CRDT, and the CRDT already
  knows where a character went. Relative positions avoid a second copy of the edit arithmetic, the same reason
  as ADR 0118.
- **The text always holds the suggested version.** Everything that reads the text (compile, the agent, the
  export) needs no change. Only the editor and the review column read the records.
- **Undo is one step.** A user who undoes their last typing gets the text and its record back together. Undo
  does not reach other members' decisions, because a decision has the origin `review-decision`, which no undo
  manager tracks.
- **Records are planned, then written.** The planner (`record.ts`) is pure: it takes the change and the
  caller's insertions and returns text and record operations in the order to apply them. It is tested as a
  table, one row per rule of spec 119 §5.2.

## Consequences

- **Replacing `ySync` is our code to keep correct.** The plugin copies the library's remote-text handling. A
  library upgrade that changes `ySync`'s behaviour needs a review of `suggest-extension.ts`.
- **Records and positions are Yjs-specific.** A relative position resolves only against its own document. A
  record whose place is gone reads as "No longer applies" and can be dismissed; it is never moved.
- **A plain edit inside someone's suggestion is a normal edit** (spec 119 §5.2). The record's positions follow
  the text, so a suggestion whose text is deleted in full becomes stale.
- **The size limit is on the deleted text.** A deletion record holds the removed text, at most 100 000
  characters. A larger deletion is refused with a notice; the text stays as it was.
- **The popover is reached by hover.** Keyboard focus shows the deletion and its text, but not Accept and
  Reject; they are on the Suggestions tab, which is keyboard reachable. Recorded in `docs/known-gaps.md`.
- **The switch lives in the editor's status line.** The spec puts it in the editor bar; it sits beside the
  presence indicators, where the session it needs is in hand.
- **Suggesting is per member and per project,** stored in `project_memberships.suggest_mode` (migration
  `c3d5f7a9b1e2`). The server accepts the switch only from members who can write the text.
