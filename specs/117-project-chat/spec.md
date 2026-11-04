# Spec 117 — Project chat (requirements)

## 1. Summary
Collaborators coordinate outside the editor today. This spec adds a per-project chat with stored messages and live
delivery, shown in a panel beside the agent. Delivery goes through a new, reusable **project event stream**: one
Server-Sent Events connection per open project, fanned out through Redis pub/sub like the compile and import
streams.

## 2. Context & dependencies
- **Depends on:** 33 (memberships), 46 and 107 (the agent window and the editor bar), 109.
- **Unlocks:** 118 (comment events), 119 (suggestion notices, if wanted).
- **Affected areas:** backend new module `discussion` (chat now, comments in 118), `projects/access`; frontend new
  module `discussion`; docs. Add the module to the module order in `backend/pyproject.toml` (above `notifications`,
  below `projects`) and to `docs/system/README.md` with a new `docs/system/discussion.md`.

## 3. Goals
- Every active member (owner, editor, viewer) reads and posts. A new capability `discussion_write`, held by all
  three roles, keeps the matrix the single source.
- Messages: plain text up to 4000 characters, Markdown rendered with the existing `react-markdown` + `remark-gfm`
  (no raw HTML), links open in a new tab.
- Live: a message appears in every open tab of every member within a second.
- History: the newest 50 on open, older pages on scroll up.
- Unread: a badge on the chat button with the count since the user's last read; opening the chat marks read.
- An author can delete their own message (shown as "Message deleted"). No editing.

## 4. Non-goals
- Direct messages, channels, reactions, attachments, typing indicators.
- E-mail for chat messages. (Mentions with notifications are in 118, for comments.)
- The agent posting into this chat.

## 5. Detailed requirements

### 5.1 Data model (one migration)
`project_chat_messages`: `id` UUID PK, `project_id` FK cascade, `author_id` FK users `SET NULL`, `body` text
(check length 1–4000), `created_at`, `deleted_at`. Index `(project_id, created_at DESC, id)`.

`project_chat_reads`: `project_id`, `user_id` (PK together, both cascade), `last_read_at`.

### 5.2 Project event stream — `backend/src/inkstave/modules/discussion/events/`
- `GET /api/v1/projects/{project_id}/events` (SSE). Auth like the compile stream (`sse_user`, token in the query);
  any active member; otherwise 404. Keep-alive comment every `COMPILE_SSE_KEEPALIVE_S`-like interval: add
  `PROJECT_EVENTS_KEEPALIVE_S` (default 15) to settings, `.env.example` and `docs/admin-guide.md`.
- Redis channel `project:events:{project_id}`. `publish_project_event(project_id, type, payload)` is the one writer,
  called **after** the commit (do not repeat the agent's "events before commit" gap).
- Frame: `event: <type>`, `data: {"type", "payload", "id"}`, where `id` is a monotonic id so the browser's
  `Last-Event-ID` can resume. On reconnect with `Last-Event-ID`, the server does not replay: the client refetches
  the latest page. State this rule in the doc.
- Event types now: `chat.message_created`, `chat.message_deleted`. Spec 118 adds `comment.*`.
- Every wait has a deadline (connection-deadline rules, ADR 0108); the stream ends when the membership is no longer
  active at the next keep-alive check (re-check the role every keep-alive, which also narrows the "open streams
  survive revocation" gap for this stream).

### 5.3 Chat API
| Method and path | Capability | Does | Errors |
|---|---|---|---|
| `GET /projects/{id}/chat/messages?before=<id>&limit=50` | `project_read` | Page, newest first, with `author {id, display_name}` | 404 |
| `POST /projects/{id}/chat/messages` `{body}` | `discussion_write` | Create, 201, publishes `chat.message_created` | 404, 403, 422, 429 |
| `DELETE /projects/{id}/chat/messages/{message_id}` | author only | Soft delete, 204, publishes `chat.message_deleted` | 403 `not_message_author`, 404 |
| `GET /projects/{id}/chat/unread` | `project_read` | `{"count"}` | 404 |
| `POST /projects/{id}/chat/read` | `project_read` | Set `last_read_at = now()`, 204 | 404 |

Rate limit `RATE_LIMIT_CHAT` (default `30/60` per user per project), documented like every setting.

### 5.4 Frontend — `frontend/src/modules/discussion/`
- `use-project-events.ts`: one `EventSource` per open project, shared by subscribers (chat now, comments later),
  with reconnect and backoff (same policy as the collab provider: 500 ms to 15 s), closed when the editor unmounts.
- `chat-panel.tsx`: a panel that opens from a chat button in the editor bar (with the unread badge). On desktop it
  takes the agent window's slot with a tab switch "Agent | Chat" (PT "Agente | Chat"); on a phone, the Agent tab
  of `MobileTabs` becomes "Agent / Chat" with the same switch. Speakers are told apart as in the agent window
  (spec commit 4d5a241): name, time, own messages aligned right.
- Optimistic send with a pending state; on failure the message stays with Retry.
- Strings in `en` and `pt` (a new `discussion` namespace).

## 6. Overleaf reference (study only — never copy)
- `services/chat/` — message storage and paging.
- `services/web/frontend/js/features/chat/` — the panel, unread count and paging up.
- `services/real-time/` — Overleaf pushes over socket.io; Inkstave uses SSE + Redis instead.

## 7. Acceptance criteria
1. A and B have the project open; A sends "Oi"; B sees it within a second without reloading.
2. B's badge shows 1 until B opens the chat.
3. A viewer can post.
4. A stranger gets 404 on every route and on the stream.
5. A removed member's stream ends at the next keep-alive.
6. Scrolling up loads older messages without duplicates.
7. A deleted message shows as deleted for everyone, live.

## 8. Test plan
- **Integration:** routes and errors; paging cursor; unread count; publish happens after commit (a failing commit
  publishes nothing); SSE stream with the in-process client used by compile SSE tests, including the role re-check;
  capability matrix test updated for `discussion_write`.
- **Vitest:** `use-project-events` sharing one `EventSource` and reconnecting; chat panel send, retry, paging,
  deleted message, unread badge.
- **Budget:** fake Redis where the compile SSE tests use it; no sleeps above 100 ms (inject the keep-alive interval).

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| Events are published only after their commit | `test_event_not_published_on_rollback` |
| Only members receive a project's events | `test_events_stream_requires_membership` |
| A stream ends when its membership ends | `test_events_stream_closes_after_removal` |
| Chat Markdown never renders raw HTML | `chat-message.test.tsx` |

## 10. Definition of Done
- [ ] §5 implemented, §7 passes, §8 green.
- [ ] New `docs/system/discussion.md` + index line; `sharing.md` lists `discussion_write`; settings documented.
- [ ] Glossary: "Project chat" → `ProjectChatMessage` → "Chat do projeto"; "Project event stream" →
      `project:events` → "—".
