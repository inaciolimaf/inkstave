# Spec 117 — Project chat (prompt)

Give the people of a project a chat of their own, next to the agent: one channel per project, saved history,
messages that arrive live, and an unread count. It also builds the **project event stream** (one SSE per
project, fed by Redis) that spec 118's comments reuse. Read `spec.md`, then implement it with its tests.

Depends on 33, 46, 107, 109. Read `docs/system/sharing.md`, `docs/system/notifications.md` and the SSE parts of
`docs/system/compile.md` first.
