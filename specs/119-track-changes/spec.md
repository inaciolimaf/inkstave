# Spec 119 — Suggest changes (track changes) (requirements)

## 1. Summary
Co-authors and advisers want to propose changes the owner can take or leave, as in Word or Google Docs. This spec
adds a per-user **Suggesting** mode. While it is on, insertions are kept in the text and recorded as suggested
insertions. Deletions remove the text and are recorded as suggested deletions with the removed text. Any member who
can write accepts or rejects each one. The text therefore always shows the suggested version: compile, the agent
and export read it unchanged.

## 2. Context & dependencies
- **Depends on:** 28–30 (CRDT, transport, roles), 110 (inline decoration styles), 118 (the review column).
- **Affected areas:** frontend `collab`, `editor`, `discussion`; backend `projects` (preference), `collab` (a test that
  the extra Yjs type survives compaction); docs. Record the model in an ADR.

## 3. Goals
- A "Suggesting" switch in the editor bar (PT "Sugerindo"), per user per project, stored on the server. Others see a
  "suggesting" mark on that person's presence.
- In Suggesting mode:
  - typed or pasted text is a **suggested insertion**, underlined in the author's colour;
  - deleted text disappears from the text and leaves a **suggested deletion** marker: a small struck-through widget
    with the removed text (folded to "…12 words" when longer than 40 characters, unfolded on hover or focus).
- Hover or focus on a suggestion: author, time, Accept, Reject.
- A "Suggestions" tab in the review column of spec 118: every suggestion of the document in text order, Accept all
  and Reject all for the document.
- Accept and reject are available to members with `collab_write` (owner, editor), including the author.
- Undo in Suggesting mode reverts the text change and its record together.

## 4. Non-goals
- Forcing Suggesting on for everyone (an owner switch): a possible later spec.
- Suggesting formatting changes, or moves.
- Viewers suggesting: viewers cannot write to the CRDT (their updates are dropped); that stays.
- Applying the agent's proposals as suggestions.

## 5. Detailed requirements

### 5.1 Model in the Yjs document
- A second shared type in each document's `Y.Doc`: `Y.Map("suggestions")`, keyed by suggestion id (UUIDv7 string).
  Values are plain objects:
  - insertion: `{kind: "insert", author_id, author_name, created_at, start, end}` where `start`/`end` are encoded
    relative positions (base64), `start` with `assoc` 0, `end` with `assoc` -1;
  - deletion: `{kind: "delete", author_id, author_name, created_at, at, text}` where `at` has `assoc` 0 and `text` is
    the removed text (at most 100 000 characters).
- The server stores and relays the whole Y.Doc already. `documents.content` is still written from `Y.Text("content")`
  only, so nothing outside the editor sees the records. Add a server test that a document with suggestions keeps
  them across `CrdtStore` compaction and reload.

### 5.2 Recording rules
| The author in Suggesting mode… | Result |
|---|---|
| types next to the end of their own open insertion | the insertion grows (its `end` is recreated) |
| types elsewhere | a new insertion |
| deletes inside their own insertion | the text goes, the insertion shrinks, no deletion record |
| deletes text that is not their own insertion | a deletion record with the removed text |
| deletes across both | split: the own-insertion part shrinks, the rest is recorded |
| deletes more than 100 000 characters | blocked, with the notice "Too much to delete as a suggestion. Turn Suggesting off to delete it." |

Edits made with Suggesting off are normal edits, even inside someone's suggestion.

### 5.3 Recording path (spike first)
- Compute the records from the CodeMirror transaction (`changes.iterChanges`, old text from `startState`), because Yjs
  delete events do not carry the removed text.
- Write the text change and the map change in **one** Yjs transaction with the binding's origin, so
  `Y.UndoManager([ytext, suggestions])` undoes both at once. If `y-codemirror.next`'s sync plugin cannot be made to do
  this, replace it with an Inkstave sync plugin in `frontend/src/modules/collab/` (keeping remote cursors) and record why
  in the ADR.
- The extension is off for viewers and while the collab session is not synced.

### 5.4 Accept and reject
| | Accept | Reject |
|---|---|---|
| insertion | delete the record | delete the resolved range, then the record |
| deletion | delete the record | insert `text` at the resolved `at`, then delete the record |

Each is one Yjs transaction with origin `review-decision`, not tracked by other users' undo managers. An unresolvable
record (its range or position gone) is shown in the panel as "No longer applies" with Dismiss.

### 5.5 Preference
- `project_memberships.suggest_mode` boolean default false (migration).
- `PATCH /api/v1/projects/{project_id}/me` `{"suggest_mode": true}`: any active member with `collab_write`, else
  403. `/permissions` returns `suggest_mode` so the editor starts in the right mode.
- Awareness state gains `suggesting: boolean`.

### 5.6 Frontend files
`frontend/src/modules/collab/suggestions/`: `model.ts` (encode, resolve, pure), `record.ts` (rules of §5.2, pure over a
`ChangeSet` + old text), `suggest-extension.ts` (transaction handling), `decorations.ts`, and in `discussion`
`suggestions-tab.tsx`. Colour tokens of spec 106; the author colour is the presence colour already used for cursors.
Strings in `en` and `pt`.

## 6. Overleaf reference (study only — never copy)
- `services/web/frontend/js/features/review-panel/` — the panel and per-change actions.
- `services/document-updater/app/js/RangesManager.js` and `RangesTracker` — Overleaf's tracked insertions and
  deletions (it stores deleted text with the change, as Inkstave will). Overleaf's ranges are offset based on its
  OT ops; Inkstave uses Yjs relative positions.
- `services/web/frontend/js/features/source-editor/extensions/track-changes.ts` — how deletions are drawn as widgets.

## 7. Acceptance criteria
1. B turns on Suggesting and types "very " before "important": A sees "very " underlined in B's colour, labelled B.
2. B deletes "old": it vanishes and a struck-through "old" marker stays at that spot for A and B.
3. A rejects the deletion: "old" is back. A accepts the insertion: the underline goes, the text stays.
4. B types inside their own insertion and deletes part of it: one insertion record, no deletion record.
5. The compiled PDF shows B's suggested text and lacks the suggested deletions.
6. Undo right after B's suggested deletion brings the text back and removes the marker.
7. After everyone closes the document and reopens it, all pending suggestions are still there.
8. A viewer sees suggestions but no Accept or Reject and no Suggesting switch.

## 8. Test plan
- **Vitest:** `record.ts` table tests for every rule of §5.2; `model.ts` resolve with two `Y.Doc`s and concurrent edits;
  accept and reject on a `Y.Text`; undo of a suggested deletion; the extension with a real `EditorView` and a local
  `Y.Doc`; panel actions.
- **Integration:** a `pycrdt` document with a `suggestions` map survives snapshot, compaction and reload; the
  preference route; `/permissions` field.
- **E2E (ask before running):** two browsers, B suggests, A accepts.
- **Budget:** CRDT tests in-memory, no sleeps.

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| The text always holds the suggested version | `record.test.ts`, compile reads `documents.content` |
| Rejecting a deletion restores exactly the removed text | `review.test.ts` |
| One undo reverts a suggestion and its record | `suggest-extension.test.ts` |
| Suggestions survive the server's compaction | `test_suggestions_map_survives_compaction` |
| Viewers cannot decide suggestions | `suggestions-tab.test.tsx` and the CRDT drop of viewer updates |

## 10. Definition of Done
- [ ] Spike result recorded in the ADR; §5 implemented, §7 passes, §8 green.
- [ ] `docs/system/collab.md` documents the second shared type; `discussion.md` the tab; `sharing.md` the preference.
- [ ] Glossary: "Suggesting mode" → `suggest_mode` → "Sugerindo"; "Suggestion" → `Suggestion` → "Sugestão";
      "Accept / Reject" → "Aceitar / Rejeitar".
