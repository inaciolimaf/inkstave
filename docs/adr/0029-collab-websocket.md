# ADR 0029 — Collab WebSocket: rooms, Redis fan-out, backpressure & close codes

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 29 — Collaboration WebSocket (JWT-authed rooms + Redis fan-out)

## Context

Spec 28 built the server-side CRDT (`DocumentManager`, the y-protocols codec,
awareness). Spec 29 is the **transport**: a FastAPI WebSocket that authenticates a
connection, joins a per-document room, and relays binary Yjs sync/update/awareness
messages between clients — including clients on *different app instances* — driving
the spec-28 manager as the single source of truth. Overleaf's `real-time` was read
for plumbing only (it relays OT ops; Inkstave relays binary CRDT).

## Decisions

### 1. Endpoint & auth in the handshake

Route `WEBSOCKET /ws/collab/projects/{project_id}/documents/{document_id}`. The
access token is a `?token=` **query param** (browsers can't set Authorization
headers on `WebSocket`). The JWT is verified via the spec-08 `authenticate_ws_token`
primitive and the project access checked **before `accept()`** — we never accept
then expose room data. Failures close during the handshake with an application
close code (no room joined).

**Authz is a collaborator stub (`TODO(spec-34)`): owner-only.** To produce the
spec's `4403` vs `4404` distinction it checks project existence then ownership
explicitly — a deliberate, documented info-leak tradeoff that is gated behind a
valid JWT (unlike the REST layer's anti-enumeration 404s).

### 2. All delivery goes through Redis (uniform sender-exclusion)

One pub/sub channel per document (`{prefix}{document_id}`). Every relayable
payload is published wrapped in a binary envelope — length-framed
`instance_id` + `origin_conn_id` + raw Yjs message. A single subscriber task per
locally-subscribed document reads the channel and calls
`RoomManager.local_broadcast(payload, exclude=origin_conn_id if envelope.instance
== this_instance else None)`. So **local and cross-instance delivery use the same
path**, and the originating socket is excluded exactly once. A per-process
`instance_id` distinguishes the loopback. This makes app instances interchangeable
with no sticky sessions.

### 3. Connection model & backpressure

Each `Connection` has a dedicated **writer task** draining a **bounded**
`send_queue` to the socket; producers (the Redis forwarder, the handshake) only
`put_nowait`. A producer that finds a queue full reports the connection as
*overflowed*; the transport then closes it with **4408** (slow consumer) — we drop
a hopeless consumer rather than block the room or grow memory. A healthy member in
the same broadcast is unaffected. A per-connection 1-second sliding-window rate
guard closes **4429** when `COLLAB_WS_MAX_MSGS_PER_SEC` is exceeded; oversize/text
frames close **4400**.

**Idle ping/pong is delegated to the ASGI server** (uvicorn's `--ws-ping-interval`
/`--ws-ping-timeout`): the ASGI/Starlette interface does not surface WS control
frames to the application, so an app-level heartbeat can't send pings. The
`COLLAB_WS_PING_*` settings + close code `4000` are reserved for that layer.

### 4. Lifecycle & cleanup

On connect: authenticate → `accept()` → `manager.acquire` (refcount++/lazy load) →
join room (subscribe to Redis if first local member) → start writer → send the
server's Sync Step 1 + the awareness snapshot → receive loop. On disconnect
(graceful or abrupt, in a `finally`): cancel the writer, publish an awareness
**offline** update for this client (`AwarenessRegistry.remove_client`),
`manager.release` (refcount--; the manager flushes/evicts), leave the room, and —
if it was the last local member — tear down the Redis subscription and drop the
document's awareness. No leaked tasks or rooms.

### 5. Close-code table

| code | meaning |
| --- | --- |
| `1000` | normal close |
| `4000` | ping timeout / connection dead (ASGI-server level) |
| `4400` | bad/oversize message |
| `4401` | unauthorized (JWT missing/invalid/expired) |
| `4403` | forbidden (not a collaborator) |
| `4404` | unknown project/document |
| `4408` | slow consumer (send buffer overflow) |
| `4429` | rate limited |

## Consequences

- New module `backend/src/inkstave/collab/ws/` (rooms, redis_bridge, components,
  router); the per-instance components are built in the app lifespan and wired
  onto `app.state.collab`. No new tables.
- New `COLLAB_WS_*` / `COLLAB_REDIS_CHANNEL_PREFIX` settings in `.env.example`.
- Tested with an in-process **ASGI WebSocket client** on the test event loop (so
  the shared transactional session works) and `fakeredis`'s async pub/sub — incl.
  a cross-instance test (two `RoomManager`/`RedisBridge` on one Redis server). No
  real network; the suite stays well under 2 minutes.
- Unlocks spec 31 (browser `y-websocket` binds here) and spec 32 (presence UI
  consumes the relayed awareness).
