# Spec 44 — Agent API & Streaming (sessions, ARQ, SSE/WebSocket)

**Type:** 🟢 feature  ·  **Phase:** AI writing agent  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements are in
   [`spec.md`](spec.md). Implement *exactly* what it describes — no more, no less.
   Prefer the simplest option consistent with `CLAUDE.md`; ask rather than invent
   scope.
2. **Confirm prerequisites.** Depends on: **41** (graph, runner, sessions/
   messages, DI `LLMClient`/`FakeLLM`) and **43** (diff materialization +
   `proposed_diffs`). Transitively 42/12/13/02/03/04. All must be green. Reuse the
   ARQ job infrastructure and async-job/status-streaming patterns established in
   the compilation specs (**22**).
3. **Study the Overleaf reference (for understanding only).** **There is none for
   the agent** — Overleaf has no AI agent, no agent chat, no streaming agent
   events. You MAY reuse Inkstave's own async-job + status-streaming conventions
   from spec 22 (independently written). Do not copy Overleaf code.
4. **Implement** the agent HTTP API (create session, post message, list proposed
   diffs), the **ARQ job** that runs the LangGraph turn, and the **event stream**
   (SSE or WebSocket) carrying tokens, tool-calls, tool-results, proposed-diff
   events, done/error, plus **cancellation**.
5. **Write the tests** listed in the Test plan. The LLM is **always** the injected
   `FakeLLM`; ARQ runs in-process/burst mode or via a worker stub — **no real API
   calls**.
6. **Verify.** Full suite passes under the 2-minute budget. Check every Acceptance
   criterion and Definition-of-Done item.
7. **Record decisions.** ADR for the transport choice (SSE vs WS) and the event
   protocol.

When all Definition-of-Done items pass, this spec is complete. Move to spec 45.

## One-line goal

A user can **start an agent chat session for a project, send a message, and watch
the agent run live** — tokens, tool calls/results, and proposed-diff events stream
to the browser while the LangGraph turn executes as an **ARQ job**, with
cancellation and full LLM mocking in tests.

## Do NOT (scope guard)

- Do not build the **chat UI** (spec 46) or the **diff-review UI** (spec 47) —
  only the API + event protocol they will consume.
- Do not change the **graph/tools/diff** internals (41–43) beyond wiring; add an
  event-sink hook if needed but keep their contracts.
- Do not add **rate limiting / cost caps / evals** — spec 49 (basic per-turn
  token/iteration caps already exist from 41).
- Do not make **real LLM network calls** in tests.
- Do not copy Overleaf source code (there is none for the agent).
