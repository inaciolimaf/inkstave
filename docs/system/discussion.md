# Project discussion

The project chat: one channel per project that its members read and post in, next to the agent, with live
delivery and an unread count. It also owns the **project event stream**, one Server-Sent Events connection per
open project fed by Redis, which the chat and the comment threads on the text (spec 118) both use. Specs 117
and 118. The comment model, with the anchors, is in [ADR 0118](../adr/0118-comment-anchors.md).

## Where it is

| File | Role |
|---|---|
| `backend/src/inkstave/modules/discussion/` | Module: public interface in `__init__.py` (`publish_project_event`, `schedule_project_event`, `project_channel`, `project_events_stream`, `MemberCheck`) |
| `backend/src/inkstave/modules/discussion/models.py` | `ProjectChatMessage`, `ProjectChatRead`, `CHAT_BODY_MAX_LENGTH` |
| `backend/src/inkstave/modules/discussion/schemas.py` | `ChatMessageRead` (a deleted message has no body), `ChatMessagePage`, `ChatMessageCreate`, `UnreadCount` |
| `backend/src/inkstave/modules/discussion/errors.py` | `ChatMessageNotFoundError` (`chat_message_not_found`), `NotMessageAuthorError` (`not_message_author`) |
| `backend/src/inkstave/modules/discussion/chat/service.py` | `ChatService`: paging, post, soft delete, unread count, mark read. Never commits |
| `backend/src/inkstave/modules/discussion/events/channel.py` | `project_channel`, `publish_project_event`, `schedule_project_event`: the one writer of the stream |
| `backend/src/inkstave/modules/discussion/events/stream.py` | `project_events_stream`, the SSE frames, the membership re-check |
| `backend/src/inkstave/modules/discussion/routes/chat.py` | The five chat routes |
| `backend/src/inkstave/modules/discussion/routes/events.py` | The stream route |
| `backend/migrations/versions/20261104_1000_d6f2a9c81b57_create_project_chat.py` | Creates both tables |
| `frontend/src/modules/discussion/` | Module: public interface in `index.ts` |
| `frontend/src/modules/discussion/use-project-events.ts` | `subscribeProjectEvents`, `useProjectEvents`, `projectEventsUrl`, `PROJECT_EVENT_TYPES`: one shared `EventSource` per project |
| `frontend/src/modules/discussion/use-chat.ts` | `useChat`: the infinite message list, live inserts and deletes, optimistic sends, retry |
| `frontend/src/modules/discussion/use-chat-unread.ts` | `useChatUnread`: the count and `markRead` |
| `frontend/src/modules/discussion/chat-panel.tsx` | `ChatPanel`: the list, the composer, paging and scroll anchoring |
| `frontend/src/modules/discussion/chat-message.tsx`, `frontend/src/modules/discussion/chat-markdown.tsx` | One message; Markdown with no raw HTML |
| `frontend/src/modules/discussion/chat-button.tsx` | `ChatButton`: the editor-bar button with the unread badge |
| `frontend/src/modules/editor/workspace-chat.tsx` | `useWorkspaceChat`: wires the button and the panel into the editor |
| `frontend/src/modules/agent/panel-parts.tsx` | `SideSwitch`: the Agent | Chat switch in the agent window |
| `backend/src/inkstave/modules/discussion/comments/` | Comment threads: `models.py` (`CommentThread`, `CommentMessage`), `service.py` (`CommentService`, no commit), `outcome.py` (`CommentOutcome`, `MentionMail`), `anchors.py` (base64 in and out), `schemas.py`, `errors.py`, `publish.py` (`CommentPublisher`, the event and e-mail after the commit) |
| `backend/src/inkstave/modules/discussion/routes/comments.py` | The comment routes |
| `backend/src/inkstave/modules/notifications/inbox/comment_hook.py` | `notify_comment_users`: the bell rows for mentions and replies |
| `backend/migrations/versions/20261104_1800_b7e1c4d9a2f6_spec118_comments.py` | Creates the two comment tables |
| `frontend/src/modules/discussion/comments/anchors.ts` | `encodeAnchor`, `resolveAnchor`: the Yjs relative positions, the only code that reads them |
| `frontend/src/modules/discussion/comments/comment-marks.ts` | `commentMarks`, `setCommentMarks`: the highlight extension, the click and `Mod-Alt-m` |
| `frontend/src/modules/discussion/comments/comments-panel.tsx` | `CommentsPanel`: the column on a wide screen, a sheet on a phone; filters and scope |
| `frontend/src/modules/discussion/comments/thread.tsx`, `frontend/src/modules/discussion/comments/composer.tsx` | One thread (messages, reply, edit, delete, resolve); the box for a new comment |
| `frontend/src/modules/discussion/comments/mention-textarea.tsx`, `frontend/src/modules/discussion/comments/mentions.ts` | The `@` member menu and the rule that turns picks into ids |
| `frontend/src/modules/discussion/comments/order.ts` | Which threads the panel lists, and in which order |
| `frontend/src/modules/discussion/comments/use-comments.ts` | `useCommentThreads` (refetch on `comment.*`), `useCommentMutations` |
| `frontend/src/modules/discussion/comments/comments-button.tsx` | `CommentsButton`: the editor-bar button with the open count |
| `frontend/src/modules/editor/workspace-comments.tsx` | `useWorkspaceComments`: wires the highlights, the button, the panel and the deep link into the editor |
| `frontend/src/modules/editor/comment-selection-button.tsx` | The "Comment" button over a selection |
| `frontend/src/modules/notifications/comment-link.ts` | Which bell rows are comments, and where they link |
| `backend/tests/integration/test_discussion_chat_api.py`, `backend/tests/integration/test_discussion_events_api.py`, `backend/tests/unit/test_discussion_events.py` | Backend tests |
| `backend/tests/integration/test_comments_api.py`, `backend/tests/unit/test_comment_anchors.py` | Comment backend tests |
| `frontend/src/modules/discussion/*.test.ts*` | Frontend tests |
| `frontend/src/modules/discussion/comments/*.test.ts*` | Comment frontend tests: anchors across two `Y.Doc`s, the highlight, the panel, the mention menu |

## Data

`project_chat_messages` (`id`, `project_id` cascade, `author_id` set null, `body` text, `created_at`,
`deleted_at`). The check `body_length` keeps `char_length(body)` between 1 and 4000. Index
`ix_project_chat_messages_project_created` on `(project_id, created_at DESC, id)`.

`project_chat_reads` (`project_id` and `user_id` cascade, primary key together, `last_read_at`). One row per
user and project, written when the chat is opened.

Migration `d6f2a9c81b57` (revises `c5e9a1b37d42`).

`comment_threads` (spec 118): `id`, `project_id` and `document_id` (a `tree_entities` row) cascade, `anchor_start`
and `anchor_end` (bytea, 1 to 256 bytes each, checked), `quoted_text`, `created_by` and `resolved_by` set null,
`created_at`, `resolved_at`. Indexes `(project_id, document_id)` and a partial one on the open threads.

`comment_messages` (spec 118): `id`, `thread_id` cascade, `author_id` set null, `body` (1 to 4000 characters,
checked), `mentions` (uuid array, active members only, written at the time), `created_at`, `edited_at`,
`deleted_at`. Index `(thread_id, created_at, id)`.

Migration `b7e1c4d9a2f6` (revises `a8d3c5e1f7b2`).

Redis: pub/sub channel `project:events:{project_id}` carries the events. A counter `project:events:seq:{project_id}`
(`INCR`, no TTL) numbers them. Nothing else is stored in Redis.

## Routes

| Method and path | Guard | What it does | Errors |
|---|---|---|---|
| `GET /api/v1/projects/{project_id}/chat/messages?before=&limit=` | `PROJECT_READ` | Newest first, 50 by default, at most 100. `before` is a message id. Returns `{items, has_more}` | 404 `project_not_found`, 404 `chat_message_not_found` (unknown or foreign cursor) |
| `POST /api/v1/projects/{project_id}/chat/messages` | `DISCUSSION_WRITE`, `RATE_LIMIT_CHAT` | Creates a message, 201. Publishes `chat.message_created` after the commit | 404, 403, 422, 429 `rate_limited` |
| `DELETE /api/v1/projects/{project_id}/chat/messages/{message_id}` | `DISCUSSION_WRITE`, author only | Soft delete, 204. Publishes `chat.message_deleted` once; a second delete is a no-op | 404 `project_not_found`, 404 `chat_message_not_found`, 403 `not_message_author` |
| `GET /api/v1/projects/{project_id}/chat/unread` | `PROJECT_READ` | `{"count"}` | 404 |
| `POST /api/v1/projects/{project_id}/chat/read` | `PROJECT_READ` | Sets `last_read_at` to the database clock, 204 | 404 |
| `GET /api/v1/projects/{project_id}/events` | any active member, checked inline | Server-Sent Events. Token in `Authorization` or `?access_token=` (`sse_user`) | 401, 404 `project_not_found` |

Comment threads (spec 118), under `/api/v1/projects/{project_id}/comments`:

| Method and path | Guard | What it does | Errors |
|---|---|---|---|
| `GET /comments?document_id=&status=open\|resolved\|all` | `PROJECT_READ` | The threads with their messages, oldest first. `status` defaults to `all`. Not paged | 404 `project_not_found` |
| `POST /comments` `{document_id, anchor_start, anchor_end, quoted_text, body, mentions}` | `DISCUSSION_WRITE`, `RATE_LIMIT_COMMENTS` | Thread and first message, 201. Publishes `comment.thread_created` | 404, 403, 422 (`validation_error` for an anchor over 256 bytes, bad base64 or a quote over 500 characters; `not_a_text_document` for a folder or file), 429 |
| `POST /comments/{thread_id}/messages` `{body, mentions}` | `DISCUSSION_WRITE`, `RATE_LIMIT_COMMENTS` | A reply, 201. Publishes `comment.message_created` | 404 `comment_thread_not_found`, 422, 429 |
| `PATCH /comments/{thread_id}/messages/{message_id}` `{body, mentions}` | `DISCUSSION_WRITE`, author only | Edit, sets `edited_at`. Publishes `comment.message_updated` | 403 `not_message_author`, 404 `comment_message_not_found` (also for a deleted message) |
| `DELETE /comments/{thread_id}/messages/{message_id}` | `DISCUSSION_WRITE`, author only | Soft delete, 204. Deleting the last live message deletes the thread. Publishes `comment.message_deleted` with `thread_deleted`; a second delete is a no-op | 403, 404 |
| `POST /comments/{thread_id}/resolve` and `/reopen` | `DISCUSSION_WRITE` | Toggle, returns the thread. A call that changes nothing publishes nothing | 404 |

Errors use the usual envelope. A stranger gets 404 `project_not_found` on every route, as for the chat.

The `comment.*` payloads: the created thread, `{thread_id, message}` for a reply or an edit, `{thread_id,
message_id, thread_deleted}` for a delete, and the thread for resolve and reopen.

## How it works

**Posting.** `post_message` (`routes/chat.py`) calls `ChatService.create_message`, which adds the row and
flushes; `created_at` is set in Python. The route then calls `schedule_project_event`, which queues
`_publish_quietly` as a FastAPI background task. The unit of work commits when its dependency exits, and
background tasks run after the response is sent. So an event leaves Redis only after its transaction committed,
and a failed commit (500) publishes nothing.

**Publishing.** `publish_project_event` increments the per-project counter for the event `id`, then publishes
`{"type", "payload", "id"}` on the channel. A failed publish is logged (`inkstave.discussion.events`), not raised:
the write is already saved.

**The stream.** `project_events_stream` subscribes to the channel first, then yields `: connected`, so the
browser's `open` fires after the subscription exists. Each event becomes a frame with `id:`, `event: <type>` and
`data: {"type", "payload", "id"}`. Idle polls send `: keep-alive` once per interval. The route checks membership
inline before the stream starts (404 for a non-member). Inside the stream, `recheck` runs at each interval
regardless of traffic: it opens a short session, calls `role_for`, and returns when the membership has ended.
The check uses a fresh session because the request's unit of work has already closed.

**Reconnect.** The server never replays. The `id:` field lets the browser send `Last-Event-ID`, which the server
ignores. A client that reconnects refetches: `useChat` invalidates the messages query and `useChatUnread`
the count, both on every `onOpen`.

**Client stream.** `subscribeProjectEvents` keeps one `EventSource` per project, with one handler set. The
first subscriber opens it and the last one closes it. An error closes the source and schedules a reconnect at a
random delay below `min(15 s, 500 ms × 2^attempt)`, the collab provider's policy. A successful open resets the
attempt counter. The token is read on each connect. `useProjectEvents` subscribes for the life of a component.

**Chat in the editor.** `useWorkspaceChat` (`frontend/src/modules/editor/workspace-chat.tsx`) keeps the
view (`agent` or `chat`) and opens the agent window on the chat view. `ChatButton` shows
`useChatUnread().count`. `AgentPanel` takes an optional `side` prop: with it, the header shows `SideSwitch`
instead of the agent title and the body is the `ChatPanel`. A phone shows the same switch in its single sheet,
and its tab reads "Agent / Chat". `ChatPanel` marks the chat read while it is the visible view and on each
message that arrives while it is visible.

**Optimistic sends.** `useChat.send` adds a pending row, then posts. On success the server message is inserted
into the list unless it is already there (the event may have arrived first). On failure the row stays with
"Not sent." and Retry, which posts the same body again.

**Unread count.** Messages from others, not deleted, with `created_at` after the user's `last_read_at`. With no
read row, every such message counts. Opening the chat writes the row.

**Comment anchors.** The browser sends each end of a selection as a Yjs relative position, base64. The start
has assoc 0 and the end assoc -1, so text typed at either edge stays outside the range. The server stores the
bytes and never decodes them (ADR 0118). `resolveAnchor` gives the range now, or `null` when the start is not
before the end or a position cannot be read. Such a thread is **detached**: the panel shows it with its quote
and "The text this comment was on was removed". History restore replaces text, so it can detach threads too.
That is accepted.

**Comment writes.** Each service method returns a `CommentOutcome`: the result, one event and the mention
e-mails. The route hands it to `CommentPublisher.emit`, which queues the event and each e-mail as background
tasks, so both leave only after the commit. An e-mail that cannot be enqueued is logged.

**Mentions.** The client sends `mentions` as ids: the members the author picked from the `@` menu. A pick
counts only while its `@Name` is still in the body. The server keeps the ids that are active members, other
than the author, each once. Each kept id gets a `comment_mention` bell row and an e-mail, sent through
`send_email_job` with the `comment_mention` template. An edit notifies only the members it newly mentions.

**Reply notifications.** A reply gives a `comment_reply` bell row to the thread's creator and to each earlier
message author who is still a member. The author and the members mentioned in that reply are left out. No
e-mail. The bell opens `/projects/{id}?thread={thread_id}`, and `useWorkspaceComments` reads that parameter
once: it opens the panel and the document, and puts the cursor on the thread.

**The comments panel.** `useWorkspaceComments` (`frontend/src/modules/editor/workspace-comments.tsx`) owns the
editor side. The highlights are a CodeMirror extension (`comment-marks.ts`) appended to the view, once, when
the view has a collaborative Y.Text (`ySyncFacet`). Without collaboration the button and the Comment offer stay
hidden. The panel is a column beside the text on a wide screen, and a sheet on a phone. Its list comes from
`orderThreads`: the open document in text order, detached threads after, then other files by name and age.
`useCommentThreads` refetches on every `comment.*` event and on each (re)connect, so the list needs no patching.

**Writing a comment needs the Y.Text, not the document's content.** Commenting never writes a CRDT update: the
panel reads the Y.Text and the thread API stores the anchors. A viewer may comment for that reason.

## Rules and guarantees

| Rule | Guarantee |
|---|---|
| Events are published only after their commit | `backend/tests/integration/test_discussion_chat_api.py::test_event_not_published_on_rollback`; `backend/tests/integration/test_discussion_chat_api.py::test_event_is_published_after_the_commit` |
| Only members receive a project's events | `backend/tests/integration/test_discussion_events_api.py::test_events_stream_requires_membership`; `backend/tests/integration/test_discussion_events_api.py::test_stream_endpoint_requires_a_token` |
| A stream ends when its membership ends | `backend/tests/integration/test_discussion_events_api.py::test_events_stream_closes_after_removal` |
| A stranger gets 404 on every chat route | `backend/tests/integration/test_discussion_chat_api.py::test_stranger_gets_404_on_every_route` |
| Only the author deletes, and deletion is soft and idempotent | `backend/tests/integration/test_discussion_chat_api.py::test_only_the_author_deletes_and_deletion_is_soft` |
| Paging has no duplicates and no gaps | `backend/tests/integration/test_discussion_chat_api.py::test_paging_is_newest_first_without_duplicates` |
| Posting is capped per user per project | `backend/tests/integration/test_discussion_chat_api.py::test_posting_is_capped_per_user_per_project` |
| Message bodies are 1 to 4000 characters after trimming | `backend/tests/integration/test_discussion_chat_api.py::test_invalid_bodies_are_422`; `backend/tests/unit/test_discussion_events.py::test_message_body_is_trimmed_and_must_have_text` |
| Chat Markdown never renders raw HTML | `frontend/src/modules/discussion/chat-message.test.tsx`, "never renders raw HTML from a message" |
| One `EventSource` per project, reconnect with backoff | `frontend/src/modules/discussion/use-project-events.test.ts`, "shares one EventSource between subscribers…" and "reconnects after a drop with backoff…" |
| The `discussion_write` capability is held by all three roles | `backend/tests/unit/test_authz_matrix.py` |
| An anchor follows its text through concurrent edits | `frontend/src/modules/discussion/comments/anchors.test.ts`, "keeps the highlight on its text when the other peer inserts before it" |
| A fully deleted range detaches, never jumps elsewhere | `frontend/src/modules/discussion/comments/anchors.test.ts`, "detaches when the whole commented text is deleted…" |
| Text typed at either edge of a range stays out of it | `frontend/src/modules/discussion/comments/anchors.test.ts`, "does not pull text typed at the very end…" and "…very start…"; `comment-marks.test.ts` |
| Commenting never writes to the document | `backend/tests/integration/test_comments_api.py::test_comment_does_not_touch_crdt` |
| Mentions reach only active members | `backend/tests/integration/test_comments_api.py::test_mentions_filtered_to_members` |
| A mention notifies in the bell and by e-mail, once | `backend/tests/integration/test_comments_api.py::test_mention_notifies_in_the_bell_and_by_email`; `test_mention_added_by_edit_notifies_once` |
| A reply notifies earlier participants in the bell only | `backend/tests/integration/test_comments_api.py::test_reply_notifies_earlier_participants_in_the_bell_only` |
| Comment routes: a stranger gets 404, a viewer may comment, only the author edits | `backend/tests/integration/test_comments_api.py::test_viewer_can_comment_and_strangers_get_404`; `test_author_edits_and_deletes_own_messages` |
| The last live message deletes its thread | `backend/tests/integration/test_comments_api.py::test_deleting_the_only_live_message_deletes_the_thread` |
| Comment events leave only after the commit | `backend/tests/integration/test_comments_api.py::test_event_is_published_after_the_commit`; `test_event_not_published_on_rollback` |
| The panel filters by status and scope and orders by text | `frontend/src/modules/discussion/comments/comments-panel.test.tsx`; `frontend/src/modules/discussion/comments/mentions-order.test.ts` |
| A comment event refetches the list over the project stream | `frontend/src/modules/discussion/comments/use-comments.test.tsx` |

Other modules import it only through its `__init__.py`: the `discussion: other modules only use its public
interface` contract in `backend/pyproject.toml`, checked by `make boundaries`.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `RATE_LIMIT_CHAT` | `30/60` | Posts per user per project, `limit/window_seconds` (policy `chat`, key `user_project`) |
| `PROJECT_EVENTS_KEEPALIVE_S` | `15` | Keep-alive interval of the project event stream, and how often it re-checks membership |
| `RATE_LIMIT_COMMENTS` | `60/60` | New comment threads and replies per user per project, `limit/window_seconds` (policy `comments`, key `user_project`) |

All three are in `.env.example` and [`docs/admin-guide.md`](../admin-guide.md).

Frontend: `VITE_AGENT_ENABLED` (see [frontend.md](frontend.md)) also hides the chat, because the chat lives in
the agent window.

## Points of attention

- **A failed live publish is lost for the others.** The write is saved, but `_publish_quietly` only logs a Redis
  error. Other open tabs see the message on their next reconnect or refetch, not before.
- **The chat is hidden with the agent.** `VITE_AGENT_ENABLED=false` removes the chat button and window, not only
  the agent. Splitting them needs a standalone window frame.
- **Layer placement differs from the spec.** Spec 117 asked for `discussion` below `projects`. It calls
  `projects` for `role_for` and `require_capability`, so it sits above `projects` in the import order.
- **Membership is checked once per interval, per open stream.** Each stream runs one short query every
  `PROJECT_EVENTS_KEEPALIVE_S` seconds. The access token is checked only at connect, as on the other streams.
- **Unread counts everything for a new member.** Without a read row, the whole history not written by the user
  counts as unread. Scoping it to the join date would need the membership's creation time.
- **Times come from two clocks on purpose.** Messages take the application clock, because every statement of
  one transaction shares `now()` and a message and a read in the same transaction would tie. Reads take
  `clock_timestamp()`.
- **Events are numbered per project, forever.** `project:events:seq:{project_id}` has no expiry; it is a few bytes
  per project.
- **Messages are never edited or purged.** Deletion keeps the row and drops the body in the API response. The
  body stays in the database until the project is deleted.
- **The event `payload` is untyped on the client.** `useChat` casts it to the chat message shape, and the
  `PROJECT_EVENT_TYPES` list must name every type the server sends. It names the `comment.*` types too.
- **Comment threads are not paged.** `GET /comments` returns every thread of the project, with all messages.
  Fine for a paper; a project with thousands of threads needs paging, and the panel needs it too.
- **A mention e-mail is sent after the commit, but not retried.** The enqueue is a background task. A failed
  enqueue is logged and the mention stays in the bell. `send_email_job` never retries either (notifications.md).
- **Edits do not repeat old mentions.** Editing a message notifies only the members it newly mentions. An
  edit that removes a mention does not notify anyone.
- **Resolve and reopen are idempotent and quiet.** A call that changes nothing returns the thread and publishes
  nothing, so two writers see one event per real change.
- **The Comment offer needs a selection and a collaborative editor.** Without the collaborative editor (the
  `collabEnabled` setting off), the comments button and the Comment offer are hidden, so no thread can be made.
- **The selected text's anchors come from the view's Y.Text.** A text that is selected while the document is
  still syncing is not commentable, because the Y.Text is not there yet. The button stays hidden until it is.
- **The panel counts open threads project-wide.** The button's badge is the number of open threads in the
  project, not in the open file, so a second file's threads raise it too.
