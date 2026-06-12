# Spec 44 — Agent API & Streaming (requirements)

## 1. Summary

This spec exposes the agent over HTTP and makes a turn **observable live**. It
adds endpoints to create an agent session for a project, post a user message,
stream the run's events to the browser, and list a session's proposed diffs. The
LangGraph turn runs as an **ARQ job** (long work off the request path); the job
publishes a typed **event stream** (`token`, `tool_call`, `tool_result`,
`diff_proposed`, `done`, `error`) over **Redis pub/sub**, which the browser
consumes via an SSE (or WebSocket) endpoint. Cancellation is supported. In tests
the LLM is always the injected `FakeLLM`, ARQ runs in burst/in-process mode, and
Redis is the fake from spec 04 — **no real API calls**.

## 2. Context & dependencies

- **Depends on:**
  - **41** — graph, `run_turn`, sessions/messages, DI `LLMClient` + `FakeLLM`,
    `get_llm_client` dependency.
  - **43** — `materialize_diffs`, `proposed_diffs` rows + repository.
  - **42/12/13** — tools and the project/document services they use.
  - **22** — async-job + status-streaming conventions (ARQ worker, Redis pub/sub,
    SSE pattern) to mirror, not duplicate divergently.
  - **34** — access control (only members of a project may use its agent).
  - **08** — current-user dependency / JWT auth.
- **Unlocks:** **46** (chat UI consumes these endpoints + events), **47**
  (diff-review UI lists/streams `diff_proposed`), **49** (adds limits on top).
- **Affected areas:** backend (agent router, ARQ job, event bus), config, tests.
  **No new tables** (reuses 41/43 schema); possibly one nullable column on
  `agent_sessions` for cancellation/run state (see §5.1).

## 3. Goals

- HTTP endpoints: create session, list sessions, get session (+messages), post
  message (enqueues a run), stream events, list proposed diffs, cancel run.
- An **ARQ job** `run_agent_turn` that loads the session, builds `AgentDeps` with
  the DI `LLMClient`, runs the graph with an **event sink**, materializes diffs
  (43), and publishes terminal events.
- A typed **event protocol** with a stable JSON shape and ordering guarantees.
- **Streaming transport** (SSE default; WebSocket acceptable) authenticated by JWT
  and authorized to the project, backed by Redis pub/sub keyed by `run_id`.
- **Cancellation**: a cancel endpoint signals the job to stop at the next safe
  checkpoint; the stream emits a terminal `error`/`cancelled` event.
- **Full mocking** in tests (FakeLLM + fake Redis + ARQ burst mode), under budget.

## 4. Non-goals (explicitly out of scope)

- **Frontend** (46/47).
- **Per-hunk apply** of diffs (47) — this spec only *lists* and *streams* diff
  proposals.
- **Rate limiting, cost ceilings, abuse controls, eval suite** — spec 49.
- **Multi-turn autonomous planning beyond one user message** — one POST = one
  agent turn (which may internally loop over tools, bounded by 41's caps).
- **Persisting the raw token stream** — only final messages (41) and diffs (43)
  are persisted; the token stream is ephemeral.

## 5. Detailed requirements

### 5.1 Data model

No new tables. Add to `agent_sessions` (one small migration) the run-tracking
fields used for cancellation and reconnection:

| Column | Type | Notes |
| --- | --- | --- |
| `active_run_id` | UUID \| null | the currently-running turn's `run_id`, or null when idle. |
| `run_state` | enum `agent_run_state` | `idle`, `queued`, `running`, `cancelling`, `done`, `error`; default `idle`. |

A `run_id` identifies one turn execution; it is the pub/sub channel key and the
cancellation key. The set of streamed events for a `run_id` is **ephemeral**
(Redis), not a table.

### 5.2 Backend / API

All routes are under `/api/projects/{project_id}/agent` and require a valid JWT
(spec 08) **and** project membership (spec 34). A non-member → `403`; unknown
project → `404`.

#### 5.2.1 `POST /api/projects/{project_id}/agent/sessions`
- **Auth:** member (editor or viewer may chat; `propose_edit` authz is enforced
  per-tool in 42).
- **Body:** `{ "title": string | null }` (optional).
- **Effect:** create an `agent_sessions` row (model = configured `AGENT_MODEL`).
- **Response 201:** `AgentSessionOut { id, project_id, title, status, model,
  run_state, created_at }`.

#### 5.2.2 `GET /api/projects/{project_id}/agent/sessions`
- List the **current user's** sessions in the project, newest first. Paginated.

#### 5.2.3 `GET /api/projects/{project_id}/agent/sessions/{session_id}`
- Return the session + its `agent_messages` (ordered by `seq`) and its open
  `proposed_diffs` summaries. `404` if not in project / not the user's session.

#### 5.2.4 `POST /api/projects/{project_id}/agent/sessions/{session_id}/messages`
- **Body:** `{ "content": string }` (1..8000 chars).
- **Preconditions:** session `run_state` must be `idle` (else `409 Conflict` — one
  active run per session).
- **Effect:** generate a `run_id`; set `run_state="queued"`, `active_run_id`;
  **enqueue** the ARQ job `run_agent_turn(session_id, run_id, user_message)`.
- **Response 202:** `{ "run_id": "...", "stream_url":
  "/api/projects/{pid}/agent/sessions/{sid}/runs/{run_id}/events" }`.
- The user message row is persisted by the job (spec 41 `run_turn`), so a failed
  enqueue leaves no orphan; alternatively persist the user row here and pass its
  id — **choose one and document**; default: **job persists it** for atomicity
  with the assistant rows.

#### 5.2.5 `GET .../runs/{run_id}/events` — the event stream
- **Transport:** **SSE** (`text/event-stream`) by default. (A WebSocket variant is
  acceptable if it reuses spec 29's WS auth; document the choice. SSE is simpler
  and one-directional, which fits.)
- **Auth:** JWT (via header or, for SSE in the browser, a short-lived token query
  param consistent with how spec 22/29 handle it).
- **Behavior:** subscribe to the Redis channel for `run_id` and forward events as
  they arrive. If the run already finished, replay a terminal `done`/`error` (the
  job writes a short-lived "last event" key so late subscribers aren't stuck).
- **Heartbeat:** periodic SSE comment/`ping` to keep the connection alive.
- **Closes** after a terminal event (`done` or `error`).

#### 5.2.6 `POST .../runs/{run_id}/cancel`
- **Effect:** set a Redis cancel flag for `run_id` and `run_state="cancelling"`.
  The job checks the flag at each safe checkpoint (between graph nodes / before
  each LLM call / before each tool) and stops, emitting a terminal `error` event
  with `code="cancelled"`. **Response 202.** Idempotent.

#### 5.2.7 `GET /api/projects/{project_id}/agent/sessions/{session_id}/diffs`
- List `proposed_diffs` for the session (optionally `?status=proposed`). Returns
  `ProposedDiffOut[]` (id, doc_id, path, stats, status, created_at) — **without**
  necessarily inlining full hunks (a `?include=hunks` flag may include them);
  applying is spec 47.

#### 5.2.8 Pydantic schemas
Define `AgentSessionOut`, `AgentMessageOut`, `PostMessageIn`, `PostMessageOut`,
`ProposedDiffOut`, and the event models in §5.4. Reuse spec 02 error envelope.

### 5.3 Frontend / UI

None. (Chat UI is spec 46; diff-review UI is spec 47.) This spec delivers only the
API + protocol they consume.

### 5.4 Real-time / jobs / external integrations

#### 5.4.1 ARQ job `run_agent_turn`
Signature (registered with the ARQ worker built in spec 22's infra):

```python
async def run_agent_turn(ctx, *, session_id: str, run_id: str, user_message: str) -> None
```

Steps:
1. Set `run_state="running"`. Publish `{type:"started", run_id}` (optional).
2. Build `AgentDeps`: resolve the DI `LLMClient` from settings (`get_llm_client`)
   — **in tests this is overridden with `FakeLLM`** (see §8), the tool registry
   (42), and an **`EventSink`** that publishes to the Redis channel for `run_id`.
3. Call the spec-41 runner `run_turn(...)`, passing the event sink so nodes emit:
   - **`token`** events as the LLM streams assistant content (use `LLMClient.stream`
     for the `plan`/`respond` LLM calls so tokens flow).
   - **`tool_call`** before a tool runs (name + args) and **`tool_result`** after
     (truncated structured result).
4. After the graph finishes, call `materialize_diffs` (43); for each created row
   publish a **`diff_proposed`** event.
5. Publish terminal **`done`** (with usage/iteration summary) or **`error`**.
6. Set `run_state` to `done`/`error`, clear `active_run_id`, write the
   short-lived "last event" key for late subscribers.
7. Honor the cancel flag at each checkpoint → terminal `error{code:"cancelled"}`.

The job must **never** make network calls except through the injected
`LLMClient`. All exceptions are caught and turned into an `error` event (with a
safe message); the job does not crash the worker.

#### 5.4.2 Event protocol
Events are JSON objects published to Redis and forwarded over SSE. Common shape:

```json
{ "type": "...", "run_id": "...", "seq": 0, "ts": "ISO-8601", ...payload }
```

`seq` is a per-run monotonically increasing integer for client ordering/dedup.

| `type` | Payload fields | Meaning |
| --- | --- | --- |
| `token` | `text` | a chunk of streamed assistant content |
| `tool_call` | `tool_call_id`, `name`, `arguments` | agent is about to run a tool |
| `tool_result` | `tool_call_id`, `name`, `ok`, `summary` | tool finished (result truncated for the wire) |
| `diff_proposed` | `diff_id`, `doc_id`, `path`, `stats` | a proposed diff was stored (43) |
| `done` | `usage`, `iterations`, `final_text` | turn finished successfully |
| `error` | `code`, `message` | turn failed or was cancelled (`code:"cancelled"`) |

Ordering guarantees: all `token`/`tool_call`/`tool_result`/`diff_proposed` events
precede the single terminal `done`/`error`. Clients should treat unknown `type`s
as ignorable (forward-compat).

#### 5.4.3 Event bus
A thin `EventSink` abstraction: `await sink.emit(event)` publishes to the Redis
channel `agent:run:{run_id}` and bumps `seq`. The SSE endpoint uses a Redis
subscriber. In tests the fake Redis (spec 04) backs both ends, or an in-memory
sink is injected — **document and provide a test-friendly sink**.

### 5.5 Configuration

| Env var | Default | Meaning |
| --- | --- | --- |
| `AGENT_STREAM_TRANSPORT` | `sse` | `sse` or `ws`. |
| `AGENT_STREAM_HEARTBEAT_S` | `15` | SSE heartbeat interval. |
| `AGENT_RUN_TTL_S` | `900` | TTL for the per-run "last event" key & cancel flag. |
| `AGENT_MAX_MESSAGE_CHARS` | `8000` | Max user message length. |

Reuse the existing `REDIS_URL` / ARQ settings from specs 02/22. Add the above to
`AgentSettings` and `.env.example`.

## 6. Overleaf reference (study only — never copy)

> **No Overleaf reference for the agent.** Overleaf has no AI agent, no agent chat
> sessions, and no streaming agent events — there is nothing to copy or translate.
> The relevant prior art is **Inkstave's own** spec **22** (compile API + ARQ job
> + status streaming), which established the ARQ worker, Redis pub/sub, and SSE
> conventions to mirror here. Spec 29 (collab WebSocket) informs the WS-auth path
> if `ws` transport is chosen. Both are independent Inkstave implementations.

## 7. Acceptance criteria

1. **Given** an authenticated project member, **when** they `POST .../sessions`,
   **then** a session is created (`run_state="idle"`) and returned; a non-member
   gets `403`, an unknown project `404`.
2. **Given** an idle session, **when** they `POST .../messages`, **then** the
   response is `202` with a `run_id` and `stream_url`, the ARQ job is enqueued, and
   `run_state` becomes `queued`/`running`. A second concurrent `POST` while a run
   is active returns `409`.
3. **Given** a `FakeLLM` scripted to stream `"Hello world"` and then stop, **when**
   the job runs and a client subscribes to the events stream, **then** the client
   receives ordered `token` events reconstructing `"Hello world"` followed by a
   single terminal `done` carrying usage and `final_text`.
4. **Given** a `FakeLLM` that scripts a `tool_call` to `read_file` then a final
   answer, **then** the stream contains a `tool_call` event (name+args) and a
   matching `tool_result` event (correlated `tool_call_id`, `ok`) before `done`.
5. **Given** a `FakeLLM` that scripts a `propose_edit`, **then** after the graph
   finishes the stream contains a `diff_proposed` event whose `diff_id` resolves to
   a real `proposed_diffs` row, and `GET .../diffs` lists it.
6. **Given** a run in progress, **when** the client `POST .../cancel`, **then** the
   job stops at the next checkpoint and the stream ends with `error{code:
   "cancelled"}`; `run_state` returns to `error`/`idle` and `active_run_id` clears.
7. **Given** a job that raises internally (forced in a test), **then** the stream
   ends with a single `error` event carrying a safe message and the worker does
   **not** crash; `run_state="error"`.
8. **Given** a client that subscribes **after** a short run already finished,
   **then** it still receives the terminal `done`/`error` (replayed from the
   short-lived last-event key) and the connection closes.
9. **Given** any test in the suite, **then** **no real OpenRouter/OpenAI request is
   made** (FakeLLM only) and Redis is the fake/in-memory backend.

## 8. Test plan

> Suite under 2 minutes. LLM is always `FakeLLM`; ARQ runs in **burst/in-process**
> mode (or the job coroutine is awaited directly); Redis is spec 04's fake or an
> in-memory `EventSink`. No real network.

- **Unit (pytest):**
  - Event model serialization; `seq`/ordering helper; `EventSink.emit` publishes
    the right channel/shape.
  - Cancel-flag checkpoint logic stops the loop deterministically.
  - Event-protocol forward-compat (unknown type ignored by the test client).
- **Integration (pytest + httpx + test DB + fake Redis):**
  - Session create/list/get authz (AC 1).
  - Post message enqueues + `409` on concurrent run (AC 2).
  - Run the job with a scripted `FakeLLM` and collect emitted events: token
    reconstruction + terminal `done` (AC 3); tool_call/tool_result correlation
    (AC 4); `diff_proposed` → real `proposed_diffs` row + `GET .../diffs` (AC 5).
  - Cancellation (AC 6); forced internal error → single `error`, worker survives
    (AC 7); late-subscriber replay (AC 8).
  - SSE endpoint: subscribe via httpx streaming, assert the event sequence and
    terminal close.
- **E2E (Playwright):** none yet (UI is 46/47; a full e2e agent flow lands in
  spec 54).
- **Performance/budget note:** FakeLLM streams a handful of deltas instantly; ARQ
  burst mode avoids a real worker process; fake Redis avoids a real broker. No
  sleeps beyond a tiny bounded heartbeat in one focused test.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] New env vars documented in `.env.example`; ADR for transport + event
      protocol added under `docs/`.
- [ ] No real LLM network calls anywhere in the test suite.
- [ ] No Overleaf code copied (there is none for the agent).
