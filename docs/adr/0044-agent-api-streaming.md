# ADR 0044 — Agent API: transport + event protocol

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 44 — Agent API & Streaming

## Context

Specs 41–43 built the agent pipeline (graph → tools → diffs) as in-process code.
Spec 44 exposes it over HTTP and makes a turn observable live: post a message,
stream the run, list proposed diffs, cancel. The long work runs as an ARQ job off
the request path (mirroring spec 22's compile pattern).

## Decisions

### 1. SSE transport over Redis pub/sub, keyed by `run_id`

A turn is one ARQ job `run_agent_turn(session_id, run_id, user_message)`. Events are
published to the Redis channel `agent:run:{run_id}` and forwarded to the browser over
**SSE** (`text/event-stream`) — one-directional, simple, and consistent with spec 22.
The stream endpoint authenticates via JWT in the header **or** a `?access_token=`
query param (EventSource can't set headers), exactly as compile SSE does. A
short-lived `agent:run:{run_id}:last` key stores the terminal event so a **late
subscriber** still gets `done`/`error` and closes. The SSE loop also re-checks that
key on idle polls to close the subscribe-vs-finish race.

### 2. Typed event protocol with a per-run `seq`

Every event is `{type, run_id, seq, ts, ...payload}`; `seq` is a per-run monotonic
counter for client ordering/dedup. Types: `token` (streamed prose), `tool_call`,
`tool_result`, `diff_proposed`, and the single terminal `done` | `error`
(`code:"cancelled"` for cancellation). All non-terminal events precede the terminal
one. Unknown types are ignorable (forward-compat). An **`EventSink`** abstraction
(`emit(type, **payload)`) owns `seq`; `RedisEventSink` publishes + persists the
terminal, `InMemoryEventSink` collects for tests.

### 3. Token events come from the completed assistant content

This is a **deliberate deviation from spec 44 §5.4.1**, which asks for
`LLMClient.stream` on the plan/respond LLM calls so tokens flow incrementally.
Instead, `plan` calls `LLMClient.complete` and, when an event sink is present,
re-chunks the completed `response.content` into `token` events
(`nodes.py` `_chunk`), rather than streaming raw provider deltas.

**Justification.** `complete()` returns the *full* response — content **and**
`tool_calls` **and** `usage` — in one object. The graph needs all three together:
tool calls drive the act node, and usage feeds the per-run budget gate (§5.2) and
the rollup. The streaming API (`FakeLLM.stream` / provider deltas) carries no tool
calls or usage, so streaming would break tool flows and make tests non-deterministic.
Re-chunking the finished content keeps tool flows correct, usage/budget accounting
exact, and tests deterministic.

**Trade-off / future work.** Clients therefore receive the prose in post-completion
chunks rather than truly incremental provider tokens; perceived latency is higher
for long responses. True incremental token streaming (while still capturing
`tool_calls`/`usage` for correctness) is an accepted future refinement, not a defect.

`act` emits `tool_call` before and `tool_result` after each tool; the job emits
`diff_proposed` per materialized diff (spec 43), then the terminal event.

### 4. Cancellation via a Redis flag + node checkpoints

`POST …/cancel` sets `agent:cancel:{run_id}`. `plan` and `act` check it at their start
(injected `should_cancel` on `AgentDeps`); on cancel they set `state.error="cancelled"`
→ route to `respond` → the job emits `error{code:"cancelled"}`. The job catches **all**
exceptions and turns them into a single `error` event — the worker never crashes
(`run_agent_turn` is registered `max_tries=1` so a handled failure isn't retried).

### 5. Run state on `agent_sessions`; one active run per session

Two columns (`active_run_id`, `run_state` ∈ idle/queued/running/cancelling/done/error)
track the run for the UI + concurrency. `POST …/messages` requires `run_state="idle"`
(else **409**) and flips it to `queued`; the job moves it to `running` then
`done`/`error`, clearing `active_run_id`. The **user message is persisted by the job**
(via spec-41 `run_turn`), so a failed enqueue leaves no orphan.

### 6. Authorization: 403 for non-member, 404 for unknown project

Per the spec, the agent routes use an in-handler `_require_member` (project exists →
404 if not; member → 403 if not) — a deliberately different contract from
`require_capability`'s 404-for-non-member. The spec-35 guard-coverage audit allowlists
these six routes with that rationale. Editor/viewer may both chat; `propose_edit`'s
editor-only check is enforced per-tool in spec 42.

## Consequences

- New `inkstave.agent.api` package (events, stream, jobs, enqueuer, routes, schemas)
  + two columns on `agent_sessions` (migration `c9d2e6f58b71`). `run_agent_turn`
  registered on the existing worker; `get_agent_enqueuer` dependency. Four env vars.
- 12 tests: event-bus/SSE units (incl. live fakeredis pub/sub + late-subscriber
  replay) and HTTP/job integration (session authz, enqueue + 409, token/tool/diff
  events, cancellation, internal-error survival). **No real LLM/network**; the job's
  sink + LLM client are injected in tests. Suite ~55s.
