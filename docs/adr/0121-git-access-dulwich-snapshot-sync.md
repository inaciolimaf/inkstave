# ADR 0121 — Git access: dulwich, snapshot-then-push, and the conflict policy

**Status:** accepted · **Phase:** 7 — Hardening, packaging & docs · **Spec:** 121

## Context

Writers want to clone a project with Git, work locally and push back. The web project stays the source
of truth. The server must serve Git's Smart HTTP protocol without a `git` binary in the images, and a push
must become ordinary edits: tree operations for files, minimal CRDT edits for text, visible live to
collaborators and recorded in history.

## Decision

**Library: dulwich, pinned at 1.2.17.** Pure Python, so the backend image needs no `git` binary. dulwich is
dual licensed (Apache-2.0 OR GPL-2.0-or-later); Inkstave uses it under **Apache-2.0**, which is compatible
with the MIT project. The pin is a release at least two weeks old, as the dependency rule asks (1.2.17 was
published 2026-10-03).

**Sync model: one branch, a snapshot before every fetch and push.**

- Each project has one bare repository under `GIT_REPOS_ROOT`, with `refs/heads/main` as its only branch
  and HEAD pointing at it. It is created on first use.
- Every `info/refs` request (either service) first snapshots the project into `main`: open CRDT rooms are
  flushed to `documents.content`, the tree is read from the database and the blob store, and a commit is made
  only when the tree differs from `main`'s tree. Two fetches with no change make one commit.
- A push is accepted only when its new commit descends from the current `main` (the snapshot the client
  saw). A web edit that the client did not pull therefore makes the push a non-fast-forward, refused with
  "Pull first: the project changed in Inkstave."
- `git_repo_state.head` mirrors `main` after each snapshot or accepted push.
- A lost repository directory is recreated from the project as a single new commit: Git history is lost,
  the project is not.
- Every repository operation for a project runs under the Redis lock `git:lock:{project_id}`, with
  `GIT_OPERATION_TIMEOUT_S` as both the lock expiry and the wait deadline, so replicas sharing the volume do
  not interleave. dulwich is synchronous: each call runs in `asyncio.to_thread` inside `asyncio.timeout`.

**Push application (all or nothing before any write).**

1. Parse the commands. Only `refs/heads/main` may be updated, and deleting it is refused.
2. Ingest the pack (`add_thin_pack`, capped at `GIT_MAX_PUSH_BYTES`) into the repository. Objects from a refused
   push stay unreferenced and harmless.
3. Check the commit descends from `main` and read the tree diff old → new with dulwich's rename detector
   (90 % similarity). Every path must pass the name rules, the zip-import path rules (no traversal, no
   separators, no system files, no names that differ only in case); files need an allowed extension, a sniffed
   type that matches it and the upload size cap; text must be valid UTF-8 under `MAX_DOCUMENT_BYTES`; symlinks
   and submodules are refused; the tree stays under `TREE_MAX_NODES`. Any failure refuses the whole push with
   one message per problem (at most 50). Nothing is written.
4. Apply the database changes in one transaction (folders, files, document rows, moves, deletes), with the
   projects services, so names and sibling rules match the web app. Renames become moves, so documents keep
   their entity id, history and labels. New upload blobs are written before the commit and removed if it
   fails; blobs they replace are removed after it.
5. Apply the text changes to each live document through `DocumentManager.apply_server_edits`, as minimal
   character edits, origin `git-push`. Each push flushes the editors' pending text before and after, so the push
   is captured as its own history version, with the pusher as author. The update is broadcast to every
   connected client.
6. Move `refs/heads/main`, record `git_repo_state.head`, set the token's `last_used_at`, write the audit line.

**Conflict policy (three-way, by alignment, not by search).** The push is a diff `old → new` of a text file,
where `old` is the blob of the previous `main`. The live text `L` is also a diff from `old` (what collaborators
changed since). Each push hunk is mapped into `L` through the alignment of `old` and `L`, so it lands where its
lines are now. A hunk whose old lines were left untouched in `L` is applied as is. A hunk that overlaps a region
collaborators changed is applied anyway, replacing that region, and the response carries a warning line
("main.tex: lines 40–52 were also edited in Inkstave; the pushed version was kept"). Hunks the push did not touch
keep the collaborators' edits. "A push never silently overwrites unpulled web edits" holds because the
fast-forward check comes first: a push built on an older snapshot is refused before any of this.

## Consequences

- The database transaction and the live-document edits are two steps. The CRDT rows reference the document
  rows (foreign keys), so the transaction commits before the live edits run. A failure between the two leaves
  the project with the pushed tree and a live document that lags; the next flush reconciles it. `main` moves
  after the live edits, so a client never sees a commit the project does not have.
- The request session commits when the route returns, so the push opens its own short sessions with
  `get_session_factory` and commits them explicitly. The unit-of-work session is still the only commit for
  ordinary requests.
- History records the origin as well as the author: migration `f2b4d6e8a0c1` adds `history_updates.origin`
  (NULL for an editor's own change). The history list shows `origin: "git-push"`, so a push is listed as a Git
  push by its author. Each capture buffer holds one origin; the push flushes before and after its capture, so
  origins never mix within a version.
- Upload-pack output is built in memory by dulwich in a worker thread and then streamed in chunks. The spec asked
  for streaming; dulwich builds the pack in one call, so the memory bound is the project size.
- Receive-pack bodies are read in full up to `GIT_MAX_PUSH_BYTES` (gzip-encoded bodies are inflated under the same
  cap). nginx's `client_max_body_size` for `/api/` must be at least that cap; `docs/admin-guide.md` says so.
- Renames combined with a large rewrite below 90 % similarity appear as a delete and an add; the history of the
  old path ends there.
- The dumb HTTP protocol is not served; `info/refs` without `service` is a 404.
- Migrations: `e7a1c3d5b9f2` creates `git_access_tokens` and `git_repo_state`; `f2b4d6e8a0c1` adds
  `history_updates.origin`.

## Alternatives considered

- **`git http-backend` behind a CGI bridge.** Needs the `git` binary in the image, which the Alpine images do
  not carry, and it writes refs before the server can validate them.
- **Dulwich's `ReceivePackHandler.handle()` with an update hook.** Its hooks are synchronous and run inside the
  pack handler; the database and the live documents are async. The handler is used only for the advertisement
  and the pack ingest, while the command handling is ours.
- **Pushing every change through a server-side merge.** Rejected: the spec makes the web project the source of
  truth and a push a fast-forward, so there is nothing to merge on the server.
- **A history origin kept only in the CRDT log.** The first draft of this ADR chose it to avoid a column. It was
  replaced because the history list cannot show an origin without joining the CRDT log, and the flush-around-capture
  rule makes a per-version column safe.
