# Spec 29 — Collaboration WebSocket (requirements)

## 1. Summary

This spec exposes the spec-28 CRDT model over the network. It adds a FastAPI
**WebSocket** endpoint that: authenticates the connection via a JWT (the spec-08
contract), joins the client to a **per-document room** (scoped within its
project), relays Yjs **sync / update / awareness** binary messages between clients
through the spec-28 `DocumentManager`, and uses **Redis pub/sub** so that clients
connected to *different app instances* still share a room. It defines the
connection lifecycle, backpressure handling, auth-failure handling, and
disconnect cleanup. Inkstave relays binary CRDT messages — Overleaf's `real-time`
service is referenced only for plumbing (rooms, presence, connect/auth flow,
Redis fan-out), as Overleaf is OT-based, not CRDT.

## 2. Context & dependencies

- **Depends on:**
  - **spec 28** (CRDT backend): `DocumentManager.acquire/release/handle_sync_step1/
    handle_update/handle_awareness/flush`, the `protocol.py` codec, and
    `AwarenessRegistry`. This spec is the transport that drives those methods.
  - **spec 08** (auth guards / sessions): the JWT verification primitive and the
    "resolve current user from a token" function. WS auth reuses it.
- **Unlocks:** **spec 31** (browser binds `y-websocket` to this endpoint),
  **spec 32** (presence UI consumes the relayed awareness), and the rest of
  Phase 4.
- **Affected areas:** backend (`backend/app/collab/ws/` — endpoint, room manager,
  redis bridge, connection model), infra (Redis already present from spec 01),
  docs (ADR). No frontend in this spec.

## 3. Goals

- A WebSocket route `GET /ws/collab/projects/{project_id}/documents/{document_id}`
  that upgrades, authenticates, authorises (collaborator stub), and joins a room.
- Authenticate via JWT supplied at connect time; reject unauthenticated/expired
  tokens during the handshake (before joining any room).
- On join, perform the **server side of the Yjs sync handshake** (send server
  Sync Step 1 and the current awareness snapshot; answer the client's Step 1 with
  Step 2) so a fresh client converges immediately.
- Relay every client message (sync update / awareness) to all *other* members of
  the same room, **including members on other app instances**, via Redis pub/sub —
  without echoing back to the sender.
- Apply incoming CRDT updates through the spec-28 manager (single source of truth)
  before/while relaying, so server state and persistence stay correct.
- Robust lifecycle: clean disconnect (graceful + abrupt), awareness "offline"
  broadcast on leave, refcount release to the manager, Redis unsubscribe, and no
  leaked tasks/rooms.
- Backpressure: a slow consumer must not block the room; bound per-connection send
  buffers and drop/disconnect a hopeless consumer instead of growing memory.

## 4. Non-goals (explicitly out of scope)

- The CRDT algorithm, persistence, compaction, text bridge — **spec 28**.
- Browser `y-websocket` binding and CodeMirror wiring — **spec 31**.
- Rendering cursors/selections/online list — **spec 32** (this spec only relays
  the awareness bytes).
- Real sharing/roles and full authz across REST/compile — **specs 33/34**. Here,
  membership is an **"is a collaborator" stub**: reuse spec-13's project-access
  check (owner/member). A `TODO(spec-34)` marks where finer roles plug in.
- Horizontal scaling concerns beyond a working Redis pub/sub fan-out (sticky
  sessions, sharding) — not required; the Redis bridge already makes instances
  interchangeable.

## 5. Detailed requirements

### 5.1 Data model

No new tables. All state is in-memory (rooms/connections) plus Redis channels
(transient). Persistence is entirely delegated to spec 28.

### 5.2 Backend / API

#### 5.2.1 WebSocket endpoint — `backend/app/collab/ws/router.py`

Route: **`WEBSOCKET /ws/collab/projects/{project_id}/documents/{document_id}`**

**Authentication (handshake):**
- The access token is provided as a query parameter `?token=<jwt>` (browsers
  cannot set Authorization headers on `WebSocket`; document this choice). Also
  accept a `Sec-WebSocket-Protocol: bearer,<jwt>` subprotocol as an alternative
  if convenient — query param is the required path.
- Before `accept()`, verify the JWT via the spec-08 primitive and resolve the
  user. On failure (missing/invalid/expired) **close with code `4401`**
  (application "unauthorized") and do not join any room. Never `accept()` then
  immediately close after exposing room data.
- **Authorisation (stub):** check the user is a collaborator on `project_id` and
  the document belongs to that project (spec-13 access check). On failure close
  with `4403` ("forbidden"). On unknown project/document close `4404`.

**Per the protocol, after `accept()`:**
1. `await manager.acquire(document_id)` (increments refcount, loads if needed).
2. Send the server's **Sync Step 1** (`encode_sync_step1(manager state vector)`)
   and the **awareness snapshot** (`encode_awareness(...)` if any).
3. Subscribe to the document's Redis channel (see §5.2.3) so updates from other
   instances are forwarded to this socket.
4. Enter the receive loop.

**Receive loop (per binary frame):**
- Decode with `protocol.read_message`.
  - `SyncStep1(sv)` → `step2, server_step1 = manager.handle_sync_step1(...)`;
    send `encode_sync_step2(step2)` then (if not already) `encode_sync_step1(...)`.
  - `SyncStep2(update)` / `SyncUpdate(update)` → `relayable =
    manager.handle_update(update, origin=connection_id)`; **publish** the relayable
    update to the Redis channel (which fans out to all instances, including local
    members other than the sender).
  - `Awareness(update)` → `relayable = manager.handle_awareness(update)`; publish
    to the Redis channel.
  - `UnknownMessage` → ignore.
- Enforce `COLLAB_MAX_UPDATE_BYTES` (spec 28) and a max frame size
  (`COLLAB_WS_MAX_FRAME_BYTES`); oversize frame → close `4400` ("bad message").
- Text frames are not expected; ignore or close `4400`.

**On disconnect (graceful or abrupt — handle `WebSocketDisconnect` and cancelled
tasks):**
1. Unsubscribe from Redis; cancel the forward task.
2. Produce and publish an awareness "offline" update for this client
   (`AwarenessRegistry.remove_client`).
3. `await manager.release(document_id)` (decrement refcount; manager handles
   flush/eviction).
4. Remove the connection from the local room; if it was the last local member of
   that room, tear down the local room and its Redis subscription.

#### 5.2.2 Connection & room model — `backend/app/collab/ws/rooms.py`

```python
@dataclass
class Connection:
    id: str                 # uuid4 hex, used as update origin
    user_id: UUID
    document_id: UUID
    websocket: WebSocket
    send_queue: asyncio.Queue[bytes]   # bounded, see backpressure
    awareness_client_id: int | None    # learned from first awareness msg

class Room:
    document_id: UUID
    connections: dict[str, Connection]
    # local membership only; cross-instance membership is via Redis

class RoomManager:
    async def join(self, conn: Connection) -> Room: ...
    async def leave(self, conn: Connection) -> None: ...
    async def local_broadcast(self, document_id: UUID, payload: bytes,
                              exclude: str | None) -> None:
        """Enqueue payload to every local connection except `exclude`."""
    def is_empty(self, document_id: UUID) -> bool: ...
```

Each `Connection` has a dedicated **writer task** draining `send_queue` to the
socket; producers (Redis forwarder, local broadcast, handshake) only enqueue.
This decouples slow sockets from the room.

#### 5.2.3 Redis pub/sub bridge — `backend/app/collab/ws/redis_bridge.py`

- One Redis channel per document: `collab:doc:{document_id}`.
- **Publish:** wrap each relayable payload with a small envelope identifying the
  **origin instance + origin connection id** so an instance can avoid re-sending to
  the originating socket. Encode the envelope as: 1 length-prefixed instance-id +
  1 length-prefixed connection-id + raw Yjs message bytes (binary; do not JSON-
  encode the payload).
- **Subscribe:** when a local room is first created for a document, the instance
  subscribes to that channel; a single background task per subscribed channel
  reads messages and calls `RoomManager.local_broadcast(document_id, payload,
  exclude=origin_conn_id_if_this_instance)`.
- **Instance id:** a per-process uuid generated at startup; used so the
  publishing instance does not double-deliver to its own originating connection
  (the local relay already excludes the sender; the Redis loopback must also
  exclude it).
- Unsubscribe when the last local connection for a document leaves.

```python
class RedisBridge:
    def __init__(self, redis, instance_id: str): ...
    async def publish(self, document_id: UUID, origin_conn_id: str,
                      payload: bytes) -> None: ...
    async def subscribe(self, document_id: UUID,
                        on_message: Callable[[bytes, str | None], Awaitable[None]]
                        ) -> "Subscription": ...
```

#### 5.2.4 Backpressure & limits

- `send_queue` is bounded (`COLLAB_WS_SEND_QUEUE_MAX`). When full, the writer is
  too slow:
  - try a short timed `put` (`COLLAB_WS_SLOW_CLIENT_TIMEOUT_MS`); on timeout,
    **close that connection** with code `4408` ("slow consumer") and clean it up.
  - Never block the room/Redis-forwarder on one slow socket.
- A per-connection inbound rate guard (`COLLAB_WS_MAX_MSGS_PER_SEC`) drops/limits
  abusive floods; exceeding it closes with `4429`.
- Idle ping/pong: send WS ping every `COLLAB_WS_PING_INTERVAL_SECONDS`; close
  `4000` if no pong within `COLLAB_WS_PONG_TIMEOUT_SECONDS` (detects dead TCP).

#### 5.2.5 Close-code table (document in code + ADR)

| code | meaning |
| --- | --- |
| `1000` | normal close |
| `4000` | ping timeout / connection dead |
| `4400` | bad/oversize message |
| `4401` | unauthorized (JWT missing/invalid/expired) |
| `4403` | forbidden (not a collaborator) |
| `4404` | unknown project/document |
| `4408` | slow consumer (send buffer overflow) |
| `4429` | rate limited |

### 5.3 Frontend / UI

None. (Browser binding is spec 31. This spec is verified with a programmatic WS
client in tests.)

### 5.4 Real-time / jobs / external integrations

- **Redis** pub/sub (already provisioned in spec 01) for cross-instance fan-out.
- **No ARQ job** — everything is in the WS request lifecycle.
- Drives **spec 28**'s `DocumentManager`/`AwarenessRegistry` as the single source
  of truth for state and persistence.

### 5.5 Configuration

Add to settings + `.env.example`:
- `COLLAB_WS_MAX_FRAME_BYTES` (default `1048576`).
- `COLLAB_WS_SEND_QUEUE_MAX` (default `256`).
- `COLLAB_WS_SLOW_CLIENT_TIMEOUT_MS` (default `2000`).
- `COLLAB_WS_MAX_MSGS_PER_SEC` (default `200`).
- `COLLAB_WS_PING_INTERVAL_SECONDS` (default `25`).
- `COLLAB_WS_PONG_TIMEOUT_SECONDS` (default `10`).
- `COLLAB_REDIS_CHANNEL_PREFIX` (default `collab:doc:`).
- Reuses spec-08 JWT settings and the existing `REDIS_URL`.

## 6. Overleaf reference (study only — never copy)

> Plumbing only. Overleaf's real-time relays OT ops; Inkstave relays binary CRDT.

- `services/real-time/app/js/Router.js` — how the WS route is wired and the
  connection handler is attached. Learn the wiring; write your own FastAPI route.
- `services/real-time/app/js/WebsocketController.js` — connect/auth flow, join,
  message dispatch, disconnect handling. Learn the lifecycle stages.
- `services/real-time/app/js/RoomManager.js` and `ConnectedUsersManager.js` —
  per-room membership and presence bookkeeping. Learn the join/leave/empty-room
  teardown; Inkstave's `RoomManager` is independent.
- `services/real-time/app/js/WebsocketLoadBalancer.js` and `ChannelManager.js` —
  the Redis pub/sub fan-out so multiple instances share a room, and how the
  originating instance avoids echoing. Learn the channel-per-room + envelope
  pattern; implement your own.
- `services/real-time/app/js/DrainManager.js` — graceful shutdown/draining of
  connections (informs the disconnect-cleanup design). Study only.

## 7. Acceptance criteria

Tested with an async WebSocket client (e.g. `httpx`/`websockets` against the
ASGI app) and a fake/ephemeral Redis (or a real test Redis from spec 04).

1. **Auth required.** Connecting without `?token=` or with an invalid/expired JWT
   results in a close with code `4401`; no room is joined and no document state is
   sent.
2. **Forbidden.** A valid token for a user who is not a collaborator on the
   project closes with `4403`; an unknown project/document closes `4404`.
3. **Handshake.** On a valid connect, the client receives a server Sync Step 1
   and (if present) an awareness snapshot before sending anything.
4. **Convergence two clients (same instance).** Two clients in the same room: an
   update sent by A is delivered to B (not echoed to A), and applying it makes B's
   reconstructed document equal A's.
5. **Cross-instance relay.** With two app instances sharing one Redis, a client on
   instance 1 and a client on instance 2 in the same room exchange an update via
   the Redis channel; the receiver applies it and converges. The sender does not
   receive its own message back.
6. **Awareness relay + offline.** An awareness update from A reaches B; when A
   disconnects, B receives an awareness update marking A offline.
7. **Persistence integration.** An update sent over the WS is applied through the
   spec-28 manager and is reflected in the persisted CRDT state (and, after the
   debounced flush, in the spec-13 text), proving the transport drives the manager.
8. **Disconnect cleanup.** After all clients leave a room, the local room is torn
   down, the Redis subscription is removed, `manager.release` drops refcount to 0,
   and no background tasks remain (assert no leaked tasks / room map empty).
9. **Backpressure.** A deliberately stalled consumer whose `send_queue` overflows
   is closed with `4408` and cleaned up, without stalling delivery to other room
   members.
10. **Oversize/bad frame.** A frame exceeding `COLLAB_WS_MAX_FRAME_BYTES` or an
    undecodable message closes with `4400`.
11. **Rate limit.** Exceeding `COLLAB_WS_MAX_MSGS_PER_SEC` closes with `4429`.
12. **Budget.** All spec-29 tests run in well under the 2-minute global budget
    (target < 15s; in-process ASGI WS client, fake/local Redis, no real network).

## 8. Test plan

> Tested with an async WS client, not a browser. Keep Redis fake or a fast local
> instance; no real network, no LLM, no LaTeX.

- **Unit (pytest):**
  - `protocol` dispatch wiring (re-uses spec-28 codec; assert each inbound type
    routes to the right manager call) via a mocked `DocumentManager`.
  - `RoomManager`: join/leave, `local_broadcast` exclude-sender, empty-room
    teardown.
  - `RedisBridge` envelope encode/decode and origin-exclusion logic (mock Redis
    pub/sub).
  - Backpressure: writer task drops/closes on full bounded queue (criterion 9
    logic) with a fake socket.
- **Integration (pytest + ASGI app + async WS client + fake/test Redis):**
  - Auth/authz close codes (criteria 1–2).
  - Handshake order (criterion 3).
  - Two-client convergence same instance (criterion 4), awareness relay + offline
    (criterion 6).
  - Persistence integration through the real spec-28 manager on the test DB
    (criterion 7) and disconnect cleanup (criterion 8).
  - **Cross-instance** (criterion 5): instantiate two app instances (two
    `RoomManager`/`RedisBridge` bound to the same Redis) in one test process and
    bridge a message between them — no second OS process needed.
  - Limit/backpressure/bad-frame close codes (criteria 9–11) with controlled
    clients.
- **Performance/budget note:** all in-process; use a fake Redis (e.g.
  `fakeredis`'s async client) or a shared test Redis; short ping/queue timeouts in
  test settings keep timing tests sub-second. Run WS integration tests with
  `pytest-asyncio`/`anyio`.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (WS endpoint, auth/authz handshake, room
      manager, Redis bridge, lifecycle, backpressure/limits, close codes).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green (including the cross-instance test).
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ruff + mypy/pyright).
- [ ] New `COLLAB_WS_*` / `COLLAB_REDIS_CHANNEL_PREFIX` env vars documented in
      `.env.example`; an ADR in `docs/` records the room/pubsub design,
      backpressure policy, and close-code table.
- [ ] No Overleaf code copied; the relay is binary CRDT, independently implemented.
