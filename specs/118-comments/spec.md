# Spec 118 — Comments on the text (requirements)

## 1. Summary
Review happens on passages. This spec adds comment threads anchored to a range of a document, kept in place across
concurrent edits by **Yjs relative positions**, with replies, resolve and reopen, and mentions that notify. Thread
text lives in Postgres; only the two anchor positions come from the CRDT, so every member, viewers included, can
comment without writing to the document.

## 2. Context & dependencies
- **Depends on:** 28–29 (Yjs document per file, `Y.Text("content")`), 39 (notifications, mailer), 117 (module
  `discussion`, capability `discussion_write`, project event stream).
- **Affected areas:** backend `discussion`, `notifications`; frontend `discussion`, `editor`; docs. Record the anchor
  model in an ADR.

## 3. Goals
- Select text → "Comment" (a button beside "Ask the agent", and `Ctrl/Cmd+Alt+M`) → write → the thread is created.
- The commented range is highlighted in the editor; clicking it opens the thread.
- A comments panel lists the document's threads in text order, filter Open / Resolved / All, and the project's
  threads with a "this file / all files" switch.
- Replies in the thread; edit and delete one's own messages.
- Resolve / reopen by any member with `discussion_write`. Resolved threads are hidden from the text by default.
- `@` in a message offers the project's members; a mention notifies that member in the bell, and by e-mail
  (template `comment_mention`, sent through the existing mailer job).
- Replies notify the thread's earlier participants in the bell only (no e-mail).
- When the commented text is deleted entirely, the thread becomes **detached**: it stays in the panel with the
  quoted text and "The text this comment was on was removed".

## 4. Non-goals
- Comments on the PDF.
- Suggesting text inside a comment (that is spec 119).
- Exporting comments into the `.tex` or zip.
- Live typing indicators in threads.

## 5. Detailed requirements

### 5.1 Anchor model
- The client computes the anchor with `Y.createRelativePositionFromTypeIndex(ytext, from, 0)` for the start
  (`assoc` ≥ 0, it sticks to the following character) and `(ytext, to, -1)` for the end (it sticks to the preceding
  character), encodes each with `Y.encodeRelativePosition`, and sends both as base64.
- The server stores them opaque. It never decodes them, so no CRDT logic on the server.
- On display, each client resolves both with `Y.createAbsolutePositionFromRelativePosition` against its live doc.
  `start >= end` or an unresolvable position → detached.
- `quoted_text` (up to 500 chars) is stored at creation for the panel, notifications and detached threads.
- History restore, which replaces text, may detach threads; that is accepted and documented.

### 5.2 Data model (one migration)
`comment_threads`: `id` UUID PK, `project_id` FK cascade, `document_id` FK `tree_entities` cascade, `anchor_start`
bytea, `anchor_end` bytea (each ≤ 256 bytes), `quoted_text` text, `created_by` FK users `SET NULL`, `created_at`,
`resolved_at`, `resolved_by`. Index `(project_id, document_id)`, partial index on open threads.

`comment_messages`: `id` UUID PK, `thread_id` FK cascade, `author_id` FK `SET NULL`, `body` text 1–4000,
`mentions` UUID[] (validated as active members at write time), `created_at`, `edited_at`, `deleted_at`.

### 5.3 API (under `/api/v1/projects/{project_id}`)
| Method and path | Capability | Does |
|---|---|---|
| `GET /comments?document_id=&status=open\|resolved\|all` | `project_read` | Threads with messages |
| `POST /comments` `{document_id, anchor_start, anchor_end, quoted_text, body}` | `discussion_write` | Thread + first message, 201 |
| `POST /comments/{thread_id}/messages` `{body}` | `discussion_write` | Reply, 201 |
| `PATCH /comments/{thread_id}/messages/{message_id}` `{body}` | author | Edit |
| `DELETE /comments/{thread_id}/messages/{message_id}` | author | Soft delete; deleting the only message deletes the thread |
| `POST /comments/{thread_id}/resolve`, `POST /comments/{thread_id}/reopen` | `discussion_write` | Toggle |

- Errors: 404 for strangers and for ids of other projects; 403 `not_message_author`; 422 for a non-doc entity or
  anchors over 256 bytes.
- Every write publishes `comment.thread_created`, `comment.message_created`, `comment.message_updated`,
  `comment.message_deleted`, `comment.thread_resolved`, `comment.thread_reopened` on the project event stream,
  after the commit.
- Mentions are parsed from a structured field, not from text: the client sends `mentions: [user_id]` with the body,
  and the body shows `@Display Name`. The server drops ids that are not active members.
- Notifications: new types `comment_mention` and `comment_reply` (add to `NotificationType`), payload with
  `project_id`, `project_name`, `thread_id`, `document_id`, `author_name`, `excerpt`. The bell opens the project at the
  thread (`/projects/{id}?thread={thread_id}`). E-mail only for mentions, never to the author themselves.
- Rate limit `RATE_LIMIT_COMMENTS` (default `60/60`), documented.

### 5.4 Frontend
- `frontend/src/modules/discussion/comments/`:
  - `anchors.ts`: encode and resolve, pure over a `Y.Text` (unit tested with two docs exchanging updates).
  - `comments-extension.ts`: mark decorations for open threads (a highlight token, stronger for the selected one),
    re-resolved on every doc change; clicking a mark selects its thread.
  - `comments-panel.tsx`: the list with filters, opened from the editor bar ("Comments" with a count of open threads,
    PT "Comentários"). On desktop a column on the right of the text (it may push the PDF narrower; the PDF stays
    visible per spec 107). On a phone a sheet.
  - `thread.tsx`: messages, reply box with `@` member picker (reuse the members list of `sharing`), resolve.
- Live updates come from `use-project-events` (spec 117).
- Strings in `en` and `pt` (`discussion` namespace); mail template text in English (known gap on e-mail language).

## 6. Overleaf reference (study only — never copy)
- `services/web/frontend/js/features/review-panel/` — the panel, thread entries, resolve flow.
- `services/document-updater/app/js/RangesManager.js` — how Overleaf keeps comment ranges in step with edits
  (Overleaf shifts offsets on its ops; Inkstave uses Yjs relative positions instead).
- `services/chat/` — threads are stored in the chat service in Overleaf.

## 7. Acceptance criteria
1. A comments on "the results" in paragraph 2; B inserts a sentence before paragraph 1; the highlight is still on
   "the results" for both.
2. Text typed at the very end of the commented range is not pulled into it.
3. B replies; A sees the reply live and gets a bell notification.
4. A writes "@B please check"; B gets a bell notification and an e-mail.
5. Resolving hides the highlight; "Resolved" filter shows the thread; reopen brings it back.
6. Deleting all of "the results" makes the thread detached, with its quote.
7. A viewer can comment; a stranger gets 404.

## 8. Test plan
- **Integration:** routes, authorization, mentions filtered to members, notifications and the e-mail enqueue (fake
  enqueuer), events after commit, thread deletion with its only message.
- **Vitest:** `anchors.ts` with two `Y.Doc`s and concurrent inserts and deletes (the core of AC 1, 2, 6); the extension
  marks; panel filters; `@` picker; live update through a fake event source.
- **Budget:** no slow test.

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| An anchor follows its text through concurrent edits | `anchors.test.ts` |
| A fully deleted range detaches, never jumps elsewhere | `anchors.test.ts` |
| Commenting never writes to the document | the API stores anchors only; `test_comment_does_not_touch_crdt` |
| Mentions reach only active members | `test_mentions_filtered_to_members` |

## 10. Definition of Done
- [ ] §5 implemented, §7 passes, §8 green.
- [ ] ADR (anchor model); `docs/system/discussion.md` and `notifications.md` updated; settings documented.
- [ ] Glossary: "Comment thread" → `CommentThread` → "Comentário"; "Resolve" → "Resolver"; "Detached comment" →
      "Comentário solto"; "Mention" → `mentions` → "Menção".
