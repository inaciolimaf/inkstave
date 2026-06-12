# ADR 0047 — Diff review UI: rebase-on-live apply through a DocumentBridge

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 47 — Diff Review UI

## Context

The agent proposes per-file unified diffs (spec 43), streamed (44) and surfaced in
chat (46). Spec 47 is the human-in-the-loop review: render each file's diff, accept or
reject **per hunk**, preview the result, and on **Apply** write only the accepted hunks
into the live document — as a CRDT update so collaborators converge. Nothing is applied
without explicit confirmation.

## Decisions

### 1. Pure hunk logic, decoupled from the DOM and the CRDT

`hunks.ts` holds the load-bearing pure functions: `rebaseHunks(content, hunks,
accepted)` locates each accepted hunk's *old* lines in the given content (offset-
tolerant search) and applies the applicable ones bottom-up, returning the target plus
the **blocked** hunk ids; `previewContent` is the same against the (clean) preview
base; `blockedAgainst` is the drift check; `minimalEdit` computes a single-region
prefix/suffix edit. All are unit-tested with hand-authored diffs — no React, no Yjs.

### 2. Rebase onto the *live* content, never the stale base

Apply doesn't trust the diff's base — it reads the document's **current live content**
and rebases each accepted hunk against it. Hunks whose expected lines no longer match
are **blocked** and excluded; the rest still apply. So a document that drifted since the
proposal is never silently clobbered (AC7). The base-changed banner is shown when any
hunk is blocked.

### 3. The CRDT write is a minimal, origin-tagged Y.Text edit

`applyTargetToYText` computes the common prefix/suffix between current and target and
writes one `delete`+`insert` in a single Yjs transaction tagged `"agent-apply"`. It is
**not** a wholesale replace, so a collaborator's concurrent edit *outside* the changed
region is preserved by the CRDT (verified by a two-`Y.Doc` convergence test, AC6).

### 4. A `DocumentBridge` is the injection seam

The review surface depends only on a `DocumentBridge` (`readContent`/`applyContent`).
Tests inject `createYDocBridge` (in-process Y.Docs); the editor injects
`createEditorBridge`, which opens a **transient collab provider per target document**
(resolving path→docId from the tree), reads/applies through its `Y.Text`, and flushes —
so the editor's own binding for an open doc, and any connected collaborator, converge
live. This keeps the whole apply path testable in-process without a collaborator server.

### 5. Confirm-gated apply; the dialog opens from the chat panel

`DiffReviewDialog` (a shadcn `Dialog`) owns `useDiffReview` (decisions default to
accepted, drift evaluated against live, preview recomputed on every toggle). **Apply**
opens an `AlertDialog` summarizing N files / M applicable hunks / K blocked — **nothing
is written until the user confirms** (AC4). The dialog is opened from spec 46's
`AgentPanel` (which has the session id) when the editor supplies a `documentBridge`, so
spec 46's `onReviewProposal` entry point plugs in without changing that spec.

### 6. One small backend addition

`ProposedDiffSummary` (spec 44) now exposes `base_version` (already on the model) so the
client can label/track the diff's base. No new endpoint — the proposal is fetched from
the existing `GET …/sessions/{sid}/diffs?include=hunks`, filtered by id.

## Consequences

- New `frontend/src/features/diff-review/` (types, hunks, crdt-apply, editor-bridge,
  api, `useDiffReview`, `DiffReviewDialog`). `base_version` added to the diff summary.
  No new env var (respects `VITE_AGENT_ENABLED`).
- 17 Vitest tests: hunk apply/rebase/blocked/minimal-edit; `applyTargetToYText` +
  two-doc convergence with a preserved concurrent edit; the dialog (load, toggle →
  counter, confirm-gated apply writing only accepted hunks, error/empty). Plus one
  stubbed Playwright flow (chat → review → diff renders). No real LLM/collab server.
