# ADR 0110 — The user applies the agent's file operations on the server

**Status:** accepted · **Phase:** 7 — Hardening, packaging & docs

## Decision

The agent proposes file operations and stores them in `proposed_file_ops`. It never carries one out.
`POST .../file-ops/{op_id}/apply`, called by the user, does the work in the backend, in one transaction,
with the caller's own role checked at that moment. No tool and no graph node can reach that code.

Document edits stay as they were: the browser applies them through the collaboration channel.

## Why not in the browser

Text edits belong in the browser because they must merge with live collaboration. A tree change has no
such need, and a browser would have to chain several calls: a move with new folders and a rename could
fail halfway and leave the project half changed. One transaction cannot.

A separate table, because `proposed_diffs.doc_id` requires an existing document and these operations
target folders and files, or something that does not exist yet.

## Consequences

- The sentence "the backend has no code path that writes for the agent" no longer holds for the tree. The
  rule that holds is the product's: nothing changes without the user's explicit request.
- Unlike diffs, these proposals record their outcome, because running one twice would fail or do harm.
- A proposal does not exist as a document, so `propose_edit` cannot reach it until it is applied.
