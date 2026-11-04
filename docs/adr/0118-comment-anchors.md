# ADR 0118 — Comment anchors are Yjs relative positions the server never reads

**Status:** accepted · **Spec:** 118

## Decision

A comment thread is anchored to a range of a document by two Yjs relative positions. The browser
computes them with `Y.createRelativePositionFromTypeIndex` (the start with assoc 0, the end with
assoc -1), encodes each with `Y.encodeRelativePosition` and sends them as base64. The server stores the
bytes in `comment_threads.anchor_start` and `anchor_end` (at most 256 bytes each) and never decodes them.
Each client resolves them against its own live document to draw the highlight.

The thread text lives in Postgres, not in the document. Commenting therefore writes no CRDT update, and a
viewer can comment without being a writer of the text.

## Why

Overleaf keeps comment ranges as character offsets and shifts them on each edit operation (its
`RangesManager`). Inkstave already has a CRDT per document, and the CRDT already knows where a character
went when another peer inserted or deleted around it. Using that knowledge avoids a second copy of the
edit arithmetic on the server.

The assoc choice gives the behaviour the spec asks for. The start sticks to the character after it, so
text typed at the start stays out of the range. The end sticks to the character before it, so text typed
at the end stays out too. When the whole range is deleted, both positions land on the same index, and the
client treats `start >= end` as detached. A position never jumps to a neighbouring passage.

Storing the anchors opaque keeps the server free of Yjs. A future Yjs upgrade changes the client only.

## Consequences

- **A thread whose text is removed is detached**, shown with its quote. Nothing is ever moved to a new
  place.
- **History restore may detach threads.** A restore replaces the text, so its anchors can collapse. This
  is accepted and documented in `docs/system/discussion.md`.
- **Resolving an anchor needs the document.** A client without the CRDT state cannot place a thread. The
  panel lists such a thread as detached until the document has synced; the editor waits for the sync before
  it shows the text, so the gap is short.
- **Yjs positions are not offsets for other tools.** The export, the PDF and the agent work on text, and
  they see no comments (spec 118 non-goal).
- **Garbage collection is not tested here.** Yjs may collect the items of deleted text. The tests cover
  deletion before the anchors are resolved, not a collected item. Whatever Yjs returns for a collected
  item, the rule is the same: a range that does not resolve is detached, and nothing moves to a neighbour.
