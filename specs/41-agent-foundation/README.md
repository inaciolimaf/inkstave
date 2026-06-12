# Spec 41 — Agent Foundation (LangGraph + OpenRouter-via-DI)

**Type:** 🟢 feature  ·  **Phase:** AI writing agent  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **02** (backend foundation:
   FastAPI app, settings, logging, error handling), **03** (database foundation:
   async SQLAlchemy, Alembic, base models), and **04** (testing foundation:
   pytest fixtures, fake Redis, 2-minute budget, CI). They must already be
   implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** **There is none.**
   Overleaf has **no AI agent feature** — there is nothing to read, copy, or
   translate. Build this purely from `spec.md`. (This is stated again in §6 of
   `spec.md`.)
4. **Implement** the backend changes described in `spec.md`: the LangGraph state
   machine scaffold, the DI-based LLM client (real OpenRouter wrapper + a
   `FakeLLM`), agent configuration/settings, and the persistence models for
   agent sessions and messages.
5. **Write the tests** listed in the spec's Test plan. The LLM is **always
   mocked** in tests via the injected `FakeLLM`; no real network calls.
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** Add a short ADR under `docs/` for the DI/LLM-client and
   graph-state design.

When all Definition-of-Done items pass, this spec is complete. Move to spec 42.

## One-line goal

Inkstave gains a runnable, server-side LangGraph agent **scaffold** — a typed
state machine with a swappable (dependency-injected) LLM client and persisted
sessions/messages — that can complete a no-tool conversational turn end to end
under a `FakeLLM` in tests.

## Do NOT (scope guard)

- Do not implement any **tools** (search/read/locate/propose) — that is spec 42.
- Do not implement **diff generation** — that is spec 43.
- Do not implement the **HTTP/streaming API or ARQ orchestration** — that is
  spec 44. (You may define the in-process `run` entry point the job will call.)
- Do not build any **frontend** — chat UI is spec 46, diff-review UI is spec 47.
- Do not copy Overleaf source code (there is none for the agent regardless).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`):
  LangChain + LangGraph, OpenAI Python SDK pointed at OpenRouter, Pydantic v2,
  SQLAlchemy 2.x async, Alembic.
