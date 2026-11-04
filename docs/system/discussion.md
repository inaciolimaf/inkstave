# Project discussion

The project chat: one channel per project that its members read and post in, next to the agent, with live
delivery and an unread count. It also owns the **project event stream**, one Server-Sent Events connection per
open project fed by Redis, which the chat uses now and comments (spec 118) will reuse. Spec 117.

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
| `backend/tests/integration/test_discussion_chat_api.py`, `backend/tests/integration/test_discussion_events_api.py`, `backend/tests/unit/test_discussion_events.py` | Backend tests |
| `frontend/src/modules/discussion/*.test.ts*` | Frontend tests |

## Data

`project_chat_messages` (`id`, `project_id` cascade, `author_id` set null, `body` text, `created_at`,
`deleted_at`). The check `body_length` keeps `char_length(body)` between 1 and 4000. Index
`ix_project_chat_messages_project_created` on `(project_id, created_at DESC, id)`.

`project_chat_reads` (`project_id` and `user_id` cascade, primary key together, `last_read_at`). One row per
user and project, written when the chat is opened.

Migration `d6f2a9c81b57` (revises `c5e9a1b37d42`).

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

The capability matrix holds `discussion_write` for owner, editor and viewer (see [sharing.md](sharing.md)).

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

Other modules import it only through its `__init__.py`: the `discussion: other modules only use its public
interface` contract in `backend/pyproject.toml`, checked by `make boundaries`.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `RATE_LIMIT_CHAT` | `30/60` | Posts per user per project, `limit/window_seconds` (policy `chat`, key `user_project`) |
| `PROJECT_EVENTS_KEEPALIVE_S` | `15` | Keep-alive interval of the project event stream, and how often it re-checks membership |

Both are in `.env.example` and [`docs/admin-guide.md`](../admin-guide.md).

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
  `PROJECT_EVENT_TYPES` list must name every type the server sends (spec 118 adds `comment.*`).
