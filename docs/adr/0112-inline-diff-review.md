# ADR 0112 — The agent's changes are reviewed in the text, and the outcome is stored

**Status:** accepted · **Phase:** 7 — Hardening, packaging & docs

## Decision

A proposal is reviewed where it applies: its removed lines are struck through in the document, its added
text is shown in green under them, and each hunk has Accept and Reject. The modal `DiffReviewDialog` is
removed (spec 110). The browser writes an accepted hunk through the collaboration channel, one minimal
edit per hunk. When the last hunk is decided, the browser posts the decisions once to
`POST .../diffs/{diff_id}/outcome`, and the server stores the status (`applied`, `partially_applied`,
`rejected` or `stale`) with the lists of hunk ids.

## Why in the text

The review has to show what the text will be. A dialog hid the text it talked about, and the demo that
approved spec 107 showed the hunks in the editor. CodeMirror decorations can draw them without changing the
document: nothing is written until a hunk is accepted, so a review that is closed changes nothing.

## Why one outcome at the end

The route takes every hunk id exactly once, so a proposal can only be recorded whole. Recording each hunk as
it is decided would need a schema for partial decisions and a route to read them back. The gap is written
down in `docs/known-gaps.md`.

## Consequences

- The server still never writes a document for the agent. The outcome route only stores what the user chose.
- A hunk whose old lines changed under the user is drawn as blocked and can only be rejected. It is recorded
  as `stale`, so a status of `stale` means the proposal no longer matched the text.
- Drawing removed lines in place (not in a block above the change) keeps them where the reader sees the
  text they replace. Added text cannot be marked in the document, since it is not there yet, so it is shown
  in a block under the change.
- The decisions of a review live in the page until the outcome is stored. A reload loses them.
