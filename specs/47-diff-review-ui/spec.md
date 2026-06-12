# Spec 47 — Diff Review UI (requirements)

## 1. Summary

This spec delivers the diff review experience for agent proposals. When the
agent proposes edits (spec 43 produces per-file unified diffs; spec 44 streams
the proposal; spec 46 surfaces a "Review changes" entry point), the user opens a
review surface that renders each file's diff, lets them **accept or reject each
hunk** (and accept/reject whole files), preview the resulting file content, and
on **Apply** writes *only the accepted hunks* into the document. Because Inkstave
documents are CRDT-backed (specs 28/31), the apply must go through the CRDT so
collaborators see the change live. Nothing is applied without explicit user
confirmation, and if the document changed since the diff's base, the UI warns and
re-bases or blocks affected hunks.

## 2. Context & dependencies

- **Depends on:**
  - spec **43** — agent diff generation. Defines the **proposal model**: a
    proposal id, and for each affected file a **base version/hash** plus a
    **unified diff** (hunks with `@@` headers, context/added/removed lines).
    This UI consumes that model; adopt spec 43's exact field names where they
    differ from the shapes below.
  - spec **46** — agent chat UI. Provides the entry point
    (`onReviewProposal(proposalId)`) that opens this surface.
  - spec **18** + the CRDT binding (specs **28/31**) — the live document and the
    Yjs text type this UI writes accepted hunks into. The apply path produces a
    CRDT update so collaborators converge on the result.
- **Unlocks:** completes the human-in-the-loop edit cycle; spec 49 audits and
  rate-limits around it; spec 50 refactors the whole feature.
- **Affected areas:** frontend (`frontend/`); a thin client-side apply module
  that uses the existing CRDT binding; docs. (No new backend tables/endpoints
  beyond fetching the proposal, which spec 44 already exposes.)

### 2.1 Proposal data shape (consumed from spec 43/44)

```ts
interface ProposedFileDiff {
  path: string;                 // project-relative file path
  baseVersion: string;          // version id / content hash the diff was cut against
  unifiedDiff: string;          // standard unified diff text for this file
  hunks: DiffHunk[];            // parsed hunks (UI may parse unifiedDiff itself)
  isNewFile?: boolean;
  isDeletion?: boolean;
}

interface DiffHunk {
  id: string;                   // stable id within the proposal
  header: string;               // "@@ -a,b +c,d @@"
  oldStart: number; oldLines: number;
  newStart: number; newLines: number;
  lines: { type: "ctx" | "add" | "del"; text: string }[];
}

interface DiffProposal {
  id: string;
  projectId: string;
  sessionId: string;
  files: ProposedFileDiff[];
  createdAt: string;
}
```

## 3. Goals

- Fetch and render a `DiffProposal` for a given `proposalId` in a focused review
  surface (dialog/sheet/route), one tab/section per affected file.
- Render each file's unified diff with clear add/remove/context styling and line
  numbers, using a CodeMirror-based or shadcn-styled diff view (own
  implementation; Overleaf history diff is layout inspiration only).
- **Per-hunk** accept/reject toggles and **per-file** accept-all / reject-all,
  with an overall accepted/total counter.
- A **preview** mode per file showing the resulting file content if the
  currently-accepted hunks were applied (computed client-side from base +
  accepted hunks).
- **Apply** (explicit, confirmed) that writes only accepted hunks into each
  document **as a CRDT update**, so collaborators see it live; rejected hunks are
  never written.
- **Base-changed detection**: before/at apply, compare each file's live document
  state against the diff's `baseVersion`; if it diverged, show a rebase/conflict
  warning and either rebase cleanly-applicable hunks or block the conflicting
  ones (never silently clobber).
- **Confirm-before-apply** dialog summarizing what will change; nothing auto
  applies.
- Clear empty/loading/error/applied states and full keyboard/SR accessibility.

## 4. Non-goals (explicitly out of scope)

- Generating diffs, running tools, or any agent logic (specs 41–44).
- The chat panel itself (spec 46) and LaTeX section/context parsing (spec 48).
- Rate limits, cost budgets, prompt-injection mitigations, audit logging, evals
  (spec 49).
- A general 3-way merge editor. Conflict handling here is: detect divergence,
  apply hunks that still apply cleanly, and warn/block the rest — not a full
  merge tool.
- Saving proposals as persistent reviewable artifacts beyond what spec 44 already
  stores; no new history entity.

## 5. Detailed requirements

### 5.1 Data model

No new database tables. Frontend state only:

```ts
interface HunkDecision { hunkId: string; accepted: boolean }

interface FileReviewState {
  path: string;
  baseVersion: string;
  decisions: Record<string /*hunkId*/, boolean>; // default: accepted = true
  baseChanged: boolean;        // live doc diverged from baseVersion
  blockedHunkIds: string[];    // hunks that no longer apply cleanly
}

interface ReviewState {
  proposal: DiffProposal | null;
  loading: boolean;
  error?: { code: string; message: string };
  files: Record<string, FileReviewState>;
  applyPhase: "idle" | "confirming" | "applying" | "applied" | "error";
}
```

Default decision for every hunk is **accepted = true** (user reviews and rejects
what they don't want); this is a UI default, not an auto-apply — apply still
requires explicit confirmation.

### 5.2 Backend / API (consumed, not built)

- **Fetch proposal** by id — via the spec-44 client (the same endpoint that
  backs the chat proposal events). If spec 44 already delivers the full proposal
  inline in the stream, the UI may use the cached payload and only re-fetch on a
  hard reload. No new endpoint is introduced by this spec.

### 5.3 Apply path (CRDT write — the load-bearing part)

Apply must converge with collaborators, so it writes through the existing CRDT
binding (specs 28/31), not via a REST overwrite.

For each affected file with at least one accepted hunk:

1. Resolve the document's live Yjs text (`Y.Text`) for `path` from the project's
   CRDT provider (open the doc if not currently open).
2. Compute the **target content** = apply accepted hunks to the file's *current
   live content* (not the stale base) using the hunks' line ranges.
3. **Base-change check:** the diff's hunks were cut against `baseVersion`. For
   each accepted hunk, verify its expected context/removed lines still match the
   live content at the hunk's location (allowing reasonable line-offset search).
   - If all accepted hunks still apply → proceed.
   - If some no longer apply → mark them `blocked`, exclude them, and surface the
     rebase/conflict warning (§5.4). Never write a blocked hunk.
4. Convert the resulting per-file edit into a **minimal CRDT mutation**: compute a
   line/char-level diff between current live content and target content and apply
   it as `Y.Text` insert/delete ops inside a single Yjs transaction (origin
   tagged, e.g. `"agent-apply"`, so it is distinguishable in history/awareness).
   - Do **not** wholesale `delete(0,len)+insert` the document — produce a minimal
     edit so concurrent edits elsewhere in the file are preserved by the CRDT.
5. Repeat per file; the apply is best-effort-atomic per file (each file's
   transaction is independent). Report a summary: applied files/hunks, blocked
   hunks, any errors.

Rejected hunks and rejected files are never written. If a file ends with zero
accepted/applicable hunks, it is skipped.

### 5.4 Frontend / UI

Entry: opened from spec 46 via `onReviewProposal(proposalId)`. Present as a
focused surface — a large shadcn `Dialog`/`Sheet` or a nested editor route
(implementer's choice; must not lose unsaved decisions on accidental dismiss —
confirm before discarding pending decisions).

Components (prefer shadcn/ui + CodeMirror 6 merge/diff styling; own
implementation):

- **`DiffReviewContainer`** — fetches/loads the proposal, owns `ReviewState`,
  renders header (proposal summary, accepted/total counter, Apply button) + a
  per-file tab list / accordion.
- **`FileDiffView`** — renders one file's unified diff: line numbers, add (green)
  / del (red) / context styling, hunk separators. New-file / deletion files are
  labelled. Use CodeMirror read-only with diff decorations or a dedicated diff
  component — not a raw `<pre>`.
- **`HunkControls`** — per hunk: an Accept/Reject toggle (checkbox or segmented
  control) and a hunk header. A `blocked` hunk is shown disabled with a "no
  longer applies" badge.
- **`FileReviewHeader`** — per file: accept-all / reject-all, accepted-hunk
  count, a **base-changed** banner when `baseChanged` is true, and a **Preview**
  toggle.
- **`FilePreview`** — read-only render of the computed resulting content for the
  current decisions (CodeMirror read-only). Updates as decisions change.
- **`ApplyConfirmDialog`** — summarizes: N files, M accepted hunks, K blocked
  hunks (excluded). Requires an explicit **Apply** click. Cancel returns to
  review with decisions intact.
- **`ApplyResultToast`/banner** — success summary or per-file error; on success
  the surface closes (or shows an "Applied" state) and the editor reflects the
  CRDT change immediately.

States:
- **Loading** proposal → `Skeleton`.
- **Error** loading → `Alert` with retry.
- **Empty** (proposal has no diffs) → friendly message, no Apply.
- **Base changed** → non-blocking banner per file; blocked hunks flagged; Apply
  still allowed for the hunks that apply, with the confirm dialog stating what is
  excluded.
- **Applying** → Apply button busy/disabled; controls locked.
- **Applied** → confirmation; the surface can be closed.

Accessibility:
- Diff lines expose add/remove semantics to SR (e.g. visually-hidden
  "added"/"removed" labels), not color alone.
- Hunk toggles and file controls keyboard-operable with visible focus; Apply and
  confirm dialog fully keyboard-navigable; dialog traps focus and restores it on
  close.

### 5.5 Configuration

- No new env vars. If a feature flag from spec 46 (`VITE_AGENT_ENABLED`) exists,
  this surface respects it. Document nothing new unless a flag is added.

## 6. Overleaf reference (study only — never copy)

- `services/web/frontend/js/features/history/` (e.g. the `diff-view/`
  components) — **layout / UX inspiration only** for how to present a document
  diff (line gutters, add/remove styling, file framing). Write your own
  components; do not copy or translate any of this AGPLv3 code.
- **The agent and the diff *review/apply* flow have NO Overleaf equivalent** —
  Overleaf has no AI agent and no agent-proposal review. The hunk-accept/reject
  model and the CRDT apply path are Inkstave-specific; build from this spec.

## 7. Acceptance criteria

1. **Given** a `proposalId` from spec 46, **when** the review surface opens,
   **then** the proposal loads and one section/tab per affected file renders its
   unified diff with add/remove/context styling and line numbers.
2. **Given** a file diff, **when** the user toggles a single hunk to **reject**,
   **then** the accepted/total counter updates and the file preview recomputes to
   exclude that hunk's changes.
3. **Given** a file diff, **when** the user clicks **reject-all** then
   **accept-all** for that file, **then** all hunks flip accordingly and the
   counter and preview reflect it.
4. **Given** decisions are set, **when** the user clicks **Apply**, **then** an
   `ApplyConfirmDialog` summarizes the change and **nothing is written** until
   the user confirms in that dialog.
5. **Given** the user confirms apply, **when** apply runs, **then** only accepted,
   applicable hunks are written into each document **as a CRDT (`Y.Text`)
   update** tagged with an agent origin, producing a minimal edit (not a full
   document replace).
6. **Given** a second collaborator is connected to the same document, **when** an
   apply is confirmed, **then** the collaborator sees the applied text appear live
   (verified via the CRDT binding, mocked/in-process in tests).
7. **Given** the live document diverged from the diff's `baseVersion`, **when**
   the surface evaluates the proposal, **then** a base-changed warning is shown,
   hunks that no longer apply cleanly are marked **blocked** and excluded, and
   blocked hunks are never written.
8. **Given** a rejected hunk or a rejected file, **when** apply runs, **then**
   those changes are never written to the document.
9. **Given** the apply completes, **when** results are computed, **then** the UI
   reports applied files/hunks and any blocked/errored items, and the editor
   reflects the new content.
10. **Given** the proposal fails to load, **when** the surface renders, **then**
    an error state with retry is shown and no document is touched.
11. **Given** keyboard-only / screen-reader use, **when** navigating the diff,
    **then** add/removed lines are conveyed non-visually and all controls
    (hunk toggles, Apply, confirm) are operable per §5.4.

## 8. Test plan

> Suite stays under 2 minutes. Use deterministic, hand-authored diffs and an
> in-process CRDT doc; no real LLM and no real collaborator server.

- **Unit (Vitest + RTL):**
  - Unified-diff parser → `DiffHunk[]` for representative diffs (single/multi
    hunk, additions-only, deletions-only, new file, deletion, trailing-newline
    edge cases).
  - Hunk-application: applying a set of accepted hunks to a base string yields the
    expected content; rejected hunks excluded.
  - Base-change detection: given a base, a diff, and a *modified* current
    content, correctly classify hunks as applicable vs blocked; never apply a
    blocked hunk.
  - Minimal-edit computation: target vs current produces a small set of
    insert/delete ops (assert it is not a full replace when only a region
    changed).
  - Components: hunk toggle updates counter + preview; accept-all/reject-all;
    confirm dialog gates apply; error/empty/loading states render.
- **Integration (Vitest, in-process Yjs doc):**
  - Bind a real `Y.Doc`/`Y.Text` (pycrdt-compatible Yjs in the browser layer) to
    a base content; run apply; assert the `Y.Text` equals the expected target and
    the transaction origin is the agent tag.
  - Two `Y.Doc`s synced in-memory: apply on doc A, assert doc B converges to the
    same content (live-collaborator behaviour) without clobbering an unrelated
    concurrent edit made on B before sync.
- **E2E (Playwright, minimal):**
  - Backend with a **FakeLLM** that emits one deterministic multi-file proposal:
    open editor → chat → "Review changes" → reject one hunk → preview updates →
    Apply → confirm → assert the editor content now contains the accepted change
    and not the rejected one. (One short spec file.)
- **Performance/budget note:** All diffs are fixtures; CRDT is in-process; the
  single Playwright file is small. No real LLM/network.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ESLint + Prettier, strict TS).
- [ ] No new env vars (or documented in `.env.example` if a flag is added).
- [ ] No Overleaf code copied (history diff used for UX ideas only; agent flow
      has no Overleaf equivalent).
