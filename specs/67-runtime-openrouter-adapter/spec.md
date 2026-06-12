# Spec 67 — Runtime safety: OpenRouter LLM adapter (mocked transport) (requirements)

## 1. Summary

This spec restores deterministic confidence in the **real** OpenRouter LLM client
wiring without a real key or network — replacing the removed live test. It adds
automated tests that drive the *actual* `OpenRouterLLMClient` code path (the
OpenAI SDK pointed at OpenRouter's base URL) against a **mocked HTTP transport**,
asserting that base URL, model, auth/identification headers, streaming and SSE
parsing are wired correctly and that stream chunks become agent tokens. It also
locks in a friendly error when the API key is absent, keeps the dependency-
injection boundary intact (so `FakeLLM` stays the default in every other test),
and **documents** (does not automate) a `just agent-live` manual smoke that runs
only when a real `OPENROUTER_API_KEY` is present and never in CI / the fast suite.

## 2. Context & dependencies

- **Depends on:**
  - Spec **41** — provider-agnostic `LLMClient` contract + `OpenRouterLLMClient`
    + `FakeLLM` + DI providers
    (`backend/src/inkstave/agent/llm/base.py`, `agent/llm/openrouter.py`,
    `agent/llm/fake.py`, `agent/dependencies.py`, `agent/deps.py`,
    `agent/settings.py`).
  - Spec **44** — streaming through the agent runner/API (consumer of
    `LLMClient.stream`).
- **Unlocks:** Safe refactors of the OpenRouter wrapper with regression coverage;
  confidence that the live path is wired before anyone runs `just agent-live`.
- **Affected areas:** backend tests (`backend/tests/`) + the `justfile` (one new
  recipe) + `docs/` (manual-smoke checklist). No production code change is
  required; if the wrapper has a real wiring bug, report it.

## 3. Goals

- Exercise the **real** `OpenRouterLLMClient.complete` and `.stream` against a
  **mocked HTTP transport** (no network), asserting:
  - the SDK targets `settings.openrouter_base_url`
    (`https://openrouter.ai/api/v1`) and posts to `/chat/completions`;
  - the request carries the configured `model`, `temperature`, `max_tokens`, the
    `Authorization: Bearer <key>` header, and the OpenRouter identification
    headers `HTTP-Referer` (`agent_http_referer`) and `X-Title` (`agent_app_title`);
  - non-streaming responses map to `LLMResponse` (content, `usage`, tool calls,
    `finish_reason`);
  - **streaming** requests set `stream=true` + `stream_options.include_usage` and
    the parsed **SSE** chunks become ordered `LLMStreamChunk`s whose deltas
    concatenate to the full text, ending with a terminal chunk carrying `usage` +
    `finish_reason`.
- Lock in a **friendly error**: constructing the client with no key raises
  `LLMError` with a clear message (no raw `KeyError`/`AttributeError`/SDK crash).
- Keep the **DI boundary** intact: a test proves `FakeLLM` satisfies the
  `LLMClient` protocol and that other suites/the app override DI to `FakeLLM`, so
  the real client is never constructed in the fast suite by default.
- **Document** a `just agent-live` manual smoke that only runs with a real key and
  is explicitly excluded from CI / the fast tier.

## 4. Non-goals (explicitly out of scope)

- No real OpenRouter call in any automated/CI test; `just agent-live` is manual.
- No change to the `LLMClient` protocol, the streaming event schema, or the agent
  graph; this spec observes the wrapper and pins behaviour.
- No tool-call *streaming* delta reassembly beyond what the current wrapper does
  (`tool_call_delta` is currently `None` in `stream`); test the existing behaviour
  and the non-streaming tool-call parse path.
- No new third-party test dependency (e.g. `respx`); use `httpx.MockTransport`,
  already available via `httpx>=0.28`.

## 5. Detailed requirements

### 5.1 Data model (if any)

None.

### 5.2 Backend / API (if any)

No new endpoints. System under test (do not change it): `OpenRouterLLMClient` in
`backend/src/inkstave/agent/llm/openrouter.py`. Key facts the tests rely on:

- Constructor raises `LLMError("OPENROUTER_API_KEY is required ...")` when
  `settings.openrouter_api_key` is falsy.
- It builds `AsyncOpenAI(api_key=..., base_url=settings.openrouter_base_url,
  timeout=settings.agent_request_timeout_s)` and stores
  `self._headers = {"HTTP-Referer": settings.agent_http_referer,
  "X-Title": settings.agent_app_title}`, passed as `extra_headers` on each call.
- `complete(...)` calls `chat.completions.create(model, messages, tools,
  temperature, max_tokens, extra_headers)` and maps `choices[0]` →
  `LLMResponse(content, tool_calls, usage, finish_reason)`; malformed tool
  arguments are recorded (`finish_reason="error"`, `_raw` arg), never raised
  (`_parse_tool_calls`).
- `stream(...)` calls `create(..., stream=True,
  stream_options={"include_usage": True})` and yields `LLMStreamChunk(delta=...,
  usage=..., finish_reason=...)` per SSE event; a usage-only trailing event yields
  a chunk with `usage` set and no delta.

**Mocking strategy (explicit — no real network).** Inject a custom
`http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))` into the
SDK. Because the production constructor does not currently accept an injected
transport, do this in tests by one of (pick the simplest that keeps the real code
path):

1. Construct `OpenRouterLLMClient(settings_with_dummy_key)`, then replace its
   `self._client` with an `AsyncOpenAI(api_key="dummy",
   base_url=settings.openrouter_base_url, http_client=httpx.AsyncClient(
   transport=httpx.MockTransport(handler)))`. This still exercises every mapping/
   parsing method on the real class (`_to_openai_messages`, `_to_openai_tools`,
   `_parse_tool_calls`, the `stream` SSE loop) — only the socket is mocked.
2. The `MockTransport` `handler(request) -> httpx.Response` inspects
   `request.url` (assert it ends with `/chat/completions` and host is
   `openrouter.ai`), `request.headers` (assert `authorization`,
   `http-referer`, `x-title`), and `json.loads(request.content)` (assert `model`,
   `temperature`, `max_tokens`, and for streaming `stream is True` +
   `stream_options.include_usage is True`). It returns:
   - for non-streaming: `httpx.Response(200, json={...chat.completion...})`;
   - for streaming: `httpx.Response(200,
     headers={"content-type": "text/event-stream"}, content=<SSE bytes>)` where
     the body is `data: {json}\n\n` lines ending with `data: [DONE]\n\n`, each
     `chat.completion.chunk` carrying a `choices[0].delta.content` and a final
     usage-bearing event.

Provide a small test helper (e.g. `_sse(*chunks: dict) -> bytes`) to build the
event stream and a builder for the non-streaming completion JSON.

### 5.3 Frontend / UI (if any)

None.

### 5.4 Real-time / jobs / external integrations (if any)

- **DI boundary.** `get_llm_client()` / `get_agent_deps()` in
  `agent/dependencies.py` construct the real `OpenRouterLLMClient`. Tests must
  confirm the app/agent suites override these (or build `AgentDeps` directly with
  `FakeLLM`) so the real client never needs a key in the fast suite. Add a test
  asserting `isinstance(FakeLLM(), LLMClient)` is True against the
  `@runtime_checkable` protocol and that `FakeLLM.stream` yields the documented
  shape (already covered in `test_agent_llm.py`; reference, don't duplicate).
- **`just agent-live` (manual smoke — NOT CI, NOT fast suite).** Add a `justfile`
  recipe that:
  - is documented as manual-only and excluded from `just test` / CI;
  - runs a single tiny live completion through the **real** client only when
    `OPENROUTER_API_KEY` is set; if unset, it prints a clear message and exits 0
    (skip), never fails CI;
  - is gated so it cannot be collected by the default pytest run — e.g. a script
    or a test marked `@pytest.mark.live` + `skipif(not os.getenv(
    "OPENROUTER_API_KEY"))`, with the `live` marker registered and deselected by
    default (`addopts = -m "not live"` or equivalent in `pyproject.toml`).
  Document it as a checklist item in `docs/` (manual release smoke), e.g.:
  `[ ] just agent-live passes with a real OPENROUTER_API_KEY (run locally, never in CI)`.

### 5.5 Configuration

- No new env vars (reuses `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`,
  `AGENT_MODEL`, etc. from `agent/settings.py`, already in `.env.example`).
- If a pytest marker is added for the live smoke, register `live` in
  `backend/pyproject.toml` `[tool.pytest.ini_options].markers` and ensure the
  default run deselects it (so the fast suite never collects a live test).

## 6. Overleaf reference (study only — never copy)

> **No Overleaf equivalent.** Overleaf has no built-in LLM/agent feature, so there
> is nothing to reference. Build entirely from Inkstave's own specs (41, 44) and
> the OpenAI/OpenRouter SDK docs. Per `CLAUDE.md`, the AI agent is Inkstave-original.

## 7. Acceptance criteria

1. **Given** a `OpenRouterLLMClient` built with a dummy key and an injected
   `httpx.MockTransport`, **when** `complete(messages, tools=...)` is called,
   **then** the mocked transport receives a POST to a URL ending
   `/chat/completions` on host `openrouter.ai`, and the request JSON contains the
   configured `model`, `temperature`, and `max_tokens`.
2. **Given** the same setup, **then** the outgoing request headers include
   `Authorization: Bearer <key>`, `HTTP-Referer` == `agent_http_referer`, and
   `X-Title` == `agent_app_title`.
3. **Given** a canned non-streaming completion response, **when** `complete` runs,
   **then** the returned `LLMResponse` has the expected `content`, `usage` (prompt/
   completion/total mapped), and `finish_reason`.
4. **Given** a response whose tool-call `arguments` is invalid JSON, **when**
   `complete` runs, **then** it does **not** raise — `finish_reason == "error"`
   and the tool call's `arguments` contains the `_raw` fallback.
5. **Given** an SSE stream of `chat.completion.chunk` events plus a trailing
   usage-only event, **when** `stream(messages)` is iterated, **then** the request
   JSON had `stream is True` and `stream_options.include_usage is True`, the
   `delta`s concatenate to the full expected text in order, and the terminal chunk
   carries `usage` and `finish_reason`.
6. **Given** the streamed chunks from AC5 fed to the agent's streaming consumer
   (or asserted directly), **then** each non-empty `delta` becomes an ordered
   agent token (the stream-chunk → token wiring is exercised, not just the raw
   SDK).
7. **Given** `AgentSettings(openrouter_api_key="")`, **when**
   `OpenRouterLLMClient(...)` is constructed, **then** it raises `LLMError` with a
   message naming `OPENROUTER_API_KEY` (friendly, not a raw SDK/attribute crash).
8. **Given** the DI providers, **then** `FakeLLM` satisfies the `LLMClient`
   protocol and the app/agent fast suites use `FakeLLM` (never construct the real
   client), so the fast suite needs no API key.
9. **Given** the default test command (`just test` / CI), **then** **no real
   network call is made and no `OPENROUTER_API_KEY` is required**; the `live`
   smoke is deselected by default and `just agent-live` is manual-only.

## 8. Test plan

> All tests combined must keep the suite under 2 minutes. The mocked-transport
> tests are in-process and add only milliseconds.

- **Unit (pytest, no DB, no network)** — new file
  `backend/tests/unit/test_openrouter_adapter.py`:
  - `test_complete_targets_openrouter_url_model_params` (AC1) — assert URL,
    `model`/`temperature`/`max_tokens` from the captured request.
  - `test_complete_sends_auth_and_identification_headers` (AC2).
  - `test_complete_maps_response_content_usage_finish` (AC3).
  - `test_complete_malformed_tool_args_do_not_raise` (AC4).
  - `test_stream_sets_stream_flags_and_parses_sse` (AC5) — build SSE via a
    `_sse(...)` helper; assert flags + concatenated deltas + terminal usage.
  - `test_stream_chunks_become_agent_tokens` (AC6) — feed the parsed chunks to the
    spec-44 stream consumer (or assert the ordered token deltas directly).
  - `test_missing_key_raises_friendly_llm_error` (AC7) — already partly covered in
    `test_agent_llm.py`; assert the message names `OPENROUTER_API_KEY`.
  - `test_fake_llm_satisfies_protocol_and_is_di_default` (AC8) — `isinstance(
    FakeLLM(), LLMClient)` and a check that `get_agent_deps` is overridable to
    `FakeLLM` (or that the app fixture already overrides it).
- **Integration:** optional — if convenient, run one mocked-transport completion
  through the agent runner to prove end-to-end token streaming (AC6) without
  network.
- **Manual smoke (NOT automated, NOT CI):** `just agent-live` — one real
  completion, runs only with `OPENROUTER_API_KEY`; skips/exits 0 otherwise.
  Documented as a release checklist item in `docs/`.
- **E2E (Playwright):** none.
- **Performance/budget note:** `httpx.MockTransport` is in-memory; the live smoke
  is excluded from the fast tier via the `live` marker / `addopts`.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (mocked-transport tests + `just agent-live`
      recipe + docs checklist).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green; run via `just test`.
- [ ] **Full suite still runs in < 2 minutes.**
- [ ] **No real external calls** and **no `OPENROUTER_API_KEY` required** in any
      automated/CI test; the `live` smoke is deselected by default.
- [ ] `FakeLLM` remains the DI default in all other tests (boundary intact).
- [ ] `just agent-live` runs only with a real key and is documented as manual-only.
- [ ] `ruff format` / `ruff check` / `mypy` clean on new files; `live` marker
      registered if used.
- [ ] No Overleaf code copied (and noted: no Overleaf equivalent exists).
- [ ] Any real wiring bug in `OpenRouterLLMClient` surfaced is reported.
