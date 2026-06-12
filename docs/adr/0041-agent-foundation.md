# ADR 0041 — Agent foundation: DI LLM client + LangGraph state

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 41 — Agent Foundation (LangGraph + OpenRouter-via-DI)

## Context

Inkstave's flagship feature is a server-side AI writing agent. This spec lays the
runnable scaffold: a LangGraph state machine, a swappable LLM client, persisted
sessions/messages, and an in-process `run_turn` entry point — no tools, no diffs, no
HTTP/streaming yet (specs 42/43/44). Overleaf has no agent, so this is built purely
from the spec.

## Decisions

### 1. The LLM is a dependency-injected interface, never imported in graph code

`agent/llm/base.py` defines a provider-agnostic contract — value objects
(`LLMMessage`, `ToolCall`, `ToolSpec`, `LLMUsage`, `LLMResponse`, `LLMStreamChunk`)
and an `LLMClient` Protocol with `complete` + `stream`. The graph and nodes depend
**only** on this interface. Two implementations:

- `OpenRouterLLMClient` wraps `openai.AsyncOpenAI` pointed at OpenRouter's base URL
  (provider/model swappable via env). It maps to/from the OpenAI chat API, parses
  `tool_calls[].function.arguments` JSON into a dict, and on malformed args records
  the raw string + `finish_reason="error"` rather than raising. All network/SDK
  errors become a typed `LLMError`. **Never instantiated in tests.**
- `FakeLLM` — deterministic, scriptable (a queue of `LLMResponse` or callables),
  records every call, and chunks scripted content into ≥2 stream deltas + a terminal
  usage/finish chunk. **Used in every test; no network anywhere in the suite.**

A lint test (`test_nodes_and_graph_do_not_import_openai`) enforces that `nodes.py`
and `graph.py` never import `openai` — the only path to a model is `deps.llm`.

`AgentSettings` (its own `BaseSettings`) loads cleanly **without** an API key; the
key is required only when `OpenRouterLLMClient` is constructed (clear `LLMError`),
so CI/tests load config without secrets.

### 2. State is a `TypedDict` with append/sum reducers

`AgentState` (LangGraph graph state) carries the running `messages` transcript
(reducer = list append, so nodes return only new messages), `pending_tool_calls`,
`iterations`, `total_tokens`, an accumulated `usage` (reducer = field-wise sum —
added beyond the spec's enumerated fields so specs 44/49 get prompt/completion
splits), `final_response`, and `error`. Pure `serialize_state`/`deserialize_state`
helpers give a JSON snapshot for persistence and the spec-44 event stream.

### 3. Graph shape + hard safety caps

`build_graph(deps)` wires `plan → (act → observe → plan)* → respond`:
`plan` calls the LLM; a conditional edge routes to `act` while there are pending
tool calls **and** caps allow, else to `respond`. With an **empty tool registry**
(this spec), any tool call is a hallucination — `act` appends a "tool unavailable"
message and clears pending, keeping the loop safe. Termination is guaranteed by
`AGENT_MAX_ITERATIONS` and `AGENT_MAX_TOTAL_TOKENS` (router forces `respond`), and
any node setting `state.error` routes straight to `respond` — the graph never
crashes. `plan` wraps the LLM call so an `LLMError` becomes a graceful error finish.

### 4. Runner: system prompt recomputed, never stored

`run_turn` loads stored `user/assistant/tool` rows, **prepends a freshly-built
system prompt** (never persisted), appends the new user message, persists the user
row, runs the graph, then persists the produced assistant/tool rows with contiguous
`seq` and the turn's aggregate usage on the final assistant row. Because the system
prompt is recomputed each run and only non-system rows are stored, re-running keeps
`seq` contiguous/unique and never duplicates the system prompt — the idempotency
property spec 44 relies on.

### 5. Persistence model

`agent_sessions` (project- and user-scoped, `status`, `model` snapshot) and
`agent_messages` (`seq` unique per session, `role`, `content`, plus `tool_calls`/
`tool_call_id`/`token_usage` JSON columns added **now** though tools land in spec 42
— so 42 needs no migration). Enum-like columns use `String` + `CheckConstraint` to
match the existing codebase convention (memberships/notifications), not native PG
enums. The system prompt is assembled from typed pieces (`prompts.py`) so 42/48 can
extend it; it explicitly states the agent **never modifies files directly** and
proposes diffs for review, with an anti-prompt-injection guardrail seed.

## Consequences

- New `inkstave.agent` package + `agent_sessions`/`agent_messages` tables (migration
  `a7b9d3e35f68`); `langgraph`, `langchain-core`, `openai` added. Nine new env vars.
- `get_llm_client()` / `get_agent_deps()` build the real client from settings (used
  by spec 44); tests build `AgentDeps` directly with `FakeLLM`.
- 15 tests (LLM/state/prompt/import-isolation/graph caps as units; runner + repo as
  integration). Zero real LLM calls; the whole suite stays ~51s.
