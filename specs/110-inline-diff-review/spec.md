# Spec 110 — Review the agent's changes inside the text (requirements)

## 1. Summary
Today a proposal card opens `DiffReviewDialog`, a modal that hides the text it talks about. This spec draws each
proposed hunk in CodeMirror itself, with accept and reject controls on the hunk, and removes the dialog. It also
closes the backend gap where `set_status` is never called: the client reports the outcome, so the proposal shows
as applied or rejected and is not offered again.

## 2. Context & dependencies
- **Depends on:** 43 (diffs), 47 (review), 75 (diff-review fix-pack), 107 (editor layout), 108 (file operations).
- **Unlocks:** 119 (track changes reuses the decoration layer's look).
- **Affected areas:** frontend `diff-review`, `editor`, `agent`; backend `agent/diffs`, `agent/routes.py`; docs.

## 3. Goals
- A proposal opens in the editor on its document, with every hunk drawn inline.
- Per hunk: Accept, Reject. For the proposal: Accept all, Reject all, Next and Previous hunk.
- Accepting a hunk writes it through the existing CRDT path (`applyTargetToYText`, origin `agent-apply`).
- The outcome is stored: `applied`, `partially_applied`, `rejected` or `stale`, with the decided hunk ids.
- A reload shows decided proposals as decided, never as pending.

## 4. Non-goals
- Applying a proposal as tracked changes (a later idea once 119 exists).
- Editing a hunk's text before accepting it. The user accepts, then edits normally.
- Reviewing file operations inline: they keep their card from spec 108.

## 5. Detailed requirements

### 5.1 Data model
- `proposed_diffs` already has `status` and an `apply_recorded` column (see `docs/system/agent.md`). Add a new
  migration only if a column is missing for `decided_hunks` (JSONB: `{"accepted": [ids], "rejected": [ids]}`) and
  `decided_at` (timestamptz) and `decided_by` (FK users, `SET NULL`).

### 5.2 Backend / API
`POST /api/v1/projects/{project_id}/agent/sessions/{session_id}/diffs/{diff_id}/outcome`

- Body: `{"accepted": ["h1", "h3"], "rejected": ["h2"], "stale": []}`. Every hunk id of the diff appears exactly
  once across the three lists; otherwise 422 `invalid_outcome`.
- Needs `DOC_WRITE` on the project at call time; the diff must belong to the session and the session to the
  project (this also closes "agent routes accept any id" for this route): otherwise 404.
- Status: all accepted → `applied`; none accepted and some stale → `stale`; none accepted → `rejected`; else
  `partially_applied`.
- A diff already decided answers 409 `already_decided` with the stored outcome.
- `GET /sessions/{session_id}` returns decided diffs with their status, so the panel draws them as decided. Remove
  the "applied diffs stay proposed and reappear on reload" entry from `docs/known-gaps.md`.
- Write the audit row `proposal_decided` through the existing audit log.

### 5.3 Frontend / UI
New files in `frontend/src/modules/diff-review/` (kebab-case):
- `inline-review-extension.ts`: a CodeMirror `StateField` of hunk decorations plus a `ViewPlugin` for the
  controls. Removed lines: a block widget above the changed region, struck through on a red tint (colour tokens
  from spec 106, never raw hex). Added text: a mark decoration on a green tint. Each hunk gets a small toolbar
  widget: ✓ Accept, ✗ Reject (aria-labels, keyboard reachable).
- `review-bar.tsx`: a bar at the top of the editor pane while a review is open: "Change 2 of 5", Previous, Next,
  Accept all, Reject all, Close. Keyboard: `Alt+]` / `Alt+[` next and previous, `Alt+Enter` accept the current
  hunk, `Alt+Backspace` reject it.
- Hunks are placed with the existing `rebaseHunks`. While the review is open, a hunk whose old lines no longer
  match the live text is drawn as **blocked** (grey, "This part changed since the proposal"), and can only be
  rejected.
- Accept writes the hunk at once through `createEditorBridge` (one transaction per hunk), so collaborators see it
  live. The decoration of the next hunks is recomputed from the new text.
- When the last hunk is decided, the client calls the outcome route and closes the review. Closing earlier keeps
  the undecided hunks pending: reopening the card resumes them.
- A proposal on a document that is not open switches the editor to it first (as `jumpToSource` does).
- Remove `DiffReviewDialog` and its tests; keep `useDiffReview`'s decision logic if it can be reused, otherwise
  delete it. No dead code left (`onReviewProposal` in `EditorWorkspace` gets a real use or goes).
- A viewer never sees accept controls (read-only), only the drawn hunks.
- Phone (390 px): the review bar wraps into two rows; hunk controls stay at least 44 px touch targets.
- All strings in `en` and `pt` (`agent` or a `review` namespace).

### 5.4 Real-time
- The decoration layer must survive remote edits: map decorations through every transaction, and re-run
  `rebaseHunks` when a remote change touches a hunk.

## 6. Overleaf reference
No equivalent: Overleaf has no agent. For the inline look, `services/web/frontend/js/features/source-editor/`
(review panel decorations of tracked changes) is a reference for decorations only.

## 7. Acceptance criteria
1. Clicking a proposal card opens its document with all hunks drawn; no modal opens.
2. Accepting one hunk changes only that region; the others stay drawn.
3. Rejecting all leaves the text unchanged and stores `rejected`.
4. A partial review stores `partially_applied` with the right ids.
5. After a reload the card says "Applied" / "Partly applied" / "Rejected" and the hunks are not drawn again.
6. A collaborator's edit inside a hunk turns it blocked; outside it, the hunk stays acceptable.
7. Keyboard alone can walk and decide every hunk; axe finds no violation in the review state.

## 8. Test plan
- **Integration:** outcome route: status mapping, 409 twice, 422 on a missing id, 404 across sessions or projects,
  403 for a viewer; session read returns decided state. Add the missing `_diff_summary` test for `?include=hunks`.
- **Vitest:** decoration placement on a fixed text; accept writes a minimal edit to a `Y.Text`; blocked hunk after a
  conflicting remote update; review bar counter and keyboard shortcuts; viewer sees no controls.
- **E2E:** one flow in `frontend/e2e/flows/` with `LLM_STUB=true` proposing two hunks, accept one, reject one,
  reload, check the card. Run only when the user allows it.

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| Nothing changes in a document until a hunk is accepted | `inline-review-extension.test.ts` |
| One accepted hunk is one minimal CRDT edit | `crdt-apply.test.ts` |
| A decided proposal is never offered again | `test_outcome_is_stored_and_listed` |
| An outcome cannot be recorded twice | `test_outcome_conflict_409` |
| A hunk that drifted can only be rejected | `inline-review-extension.test.ts` |

## 10. Definition of Done
- [ ] §5 implemented, §7 passes, §8 green, suite within budget, `make web-budget` passes.
- [ ] `docs/system/agent.md` and `docs/system/frontend.md` describe the inline review; the "reviewed in a dialog"
      and "applied diffs stay proposed" entries removed from `docs/known-gaps.md`.
- [ ] Glossary: "Inline review" → `inline-review-extension` → "Revisão no texto".
