# Spec 67 — Runtime safety: OpenRouter LLM adapter (mocked transport)

**Type:** 🟢 feature (tests-only + one manual checklist recipe)  ·  **Phase:** Runtime safety (fast tier)  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements are in
   [`spec.md`](spec.md). Implement *exactly* what it describes. This spec is
   primarily **automated tests**, plus a documented (non-CI) manual smoke recipe.
   The provider here is **OpenRouter via the OpenAI SDK** — read the LLM client
   code before touching anything; do not answer from memory.
2. **Confirm prerequisites.** Depends on spec **41** (LLM client contract +
   `OpenRouterLLMClient` + `FakeLLM` + DI) and spec **44** (streaming through the
   agent). These exist and pass.
3. **Study the existing code (for understanding only).** Relevant code lives in
   `backend/src/inkstave/agent/llm/` (`base.py`, `openrouter.py`, `fake.py`) and
   `agent/dependencies.py` / `agent/deps.py` / `agent/settings.py`. No Overleaf
   reference exists for the AI agent — build from the spec.
4. **Write the tests** listed in the spec's Test plan. Exercise the **real**
   `OpenRouterLLMClient` code path against a **mocked HTTP transport**
   (`httpx.MockTransport` injected into `AsyncOpenAI`), returning canned
   non-streaming JSON and **SSE** chunks. **No real key, no real network.**
5. **Add the manual recipe.** Add a `just agent-live` recipe (documented, NOT run
   in CI / the fast suite) that runs a single live smoke only when a real
   `OPENROUTER_API_KEY` is present, and skips loudly otherwise.
6. **Verify.** Run `just test`. It must pass and stay under 2 minutes. Check every
   Acceptance criterion and Definition-of-Done item.

When all Definition-of-Done items pass, this spec is complete. Move to spec 68.

## One-line goal

The real `OpenRouterLLMClient` wiring (base URL, model, headers, streaming, SSE
parsing) is verified deterministically with a mocked HTTP transport and no API
key, a missing-key path gives a friendly error, the DI boundary keeps `FakeLLM`
the default everywhere else, and a real-key-only `just agent-live` smoke is
documented but never runs in CI.

## Do NOT (scope guard)

- Do not make any real network call or require a real `OPENROUTER_API_KEY` in any
  automated/CI test.
- Do not change the DI boundary so that the real client leaks into other tests.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`); reuse
  `httpx` (already a dependency) for the mock transport — do **not** add `respx`.
- Do not implement later-spec features.
