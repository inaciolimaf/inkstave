# Refactor 45 — Agent Core (specs 41–44 hardening)

A review pass over the agent core (LangGraph foundation, tools, diff generation,
API/streaming). Findings came from a structured read-only audit + a DI-boundary grep;
each was judged on risk vs. value and the worthwhile fixes applied. **No features.**
Suite: **686 passed / 1 skipped in 55s** (was 680/52s) — under the 2-minute budget.
ruff + mypy (172 files) clean. DI boundary verified: `import openai` / `from openai`
appears **only** in `agent/llm/openrouter.py`.

## Applied fixes

| # | Area | File | Severity | Fix | Test |
|---|------|------|----------|-----|------|
| 1 | Graph / persisted history | `agent/nodes.py` (`respond`) | **bug** | A turn capped by `max_iterations`/`max_total_tokens` while the assistant message carried both content **and** a tool call duplicated that content into a second assistant row (and mis-attributed usage to the copy). `respond` now **reuses** the existing assistant content (sets `final_response` without appending) and only synthesizes a closing message when the transcript has no usable assistant content. | `test_refactor_45.py::test_capped_turn_does_not_duplicate_assistant` |
| 2 | Tools / cost | `agent/tools/read_file.py` | **risk** (cost/DoS-shaped) | The char cap (`AGENT_TOOL_READ_MAX_CHARS`) was bypassed on the **windowed** read path — a `read_file(start=0, end=line_count)` pulled the whole document uncapped. The cap (`_cap_to_chars`, with a single-huge-line guard) now applies to **both** the windowed and whole-doc paths. | `test_refactor_45.py::test_read_file_windowed_respects_cap` |
| 3 | API / HTTP semantics | `agent/api/routes.py` | smell/bug | A too-long user message returned **409** (a state-conflict code reserved for "run active"). It now returns **400** via a dedicated `MessageTooLongError`. | `test_agent_api.py::test_too_long_message_is_400` |

## Coverage added (closing real gaps)

| Gap | Test |
|-----|------|
| `AGENT_MAX_TOTAL_TOKENS` was never exercised (FakeLLM reported zero usage), so the graceful token-cap stop was untested (AC4). | `test_refactor_45.py::test_token_cap_ends_turn_without_exception` |
| `AGENT_MAX_TOKENS_PER_CALL` wiring through `plan → llm.complete` was unverified (AC4); `FakeLLM.calls` now records `max_tokens`/`temperature`. | `test_refactor_45.py::test_per_call_max_tokens_is_passed` |
| Import isolation only checked `nodes`/`graph` (AC2); now scans the **whole** `agent` package. | `test_agent_core.py::test_only_openrouter_imports_openai` |
| **Prompt-injection regression** (AC3): an adversarial "ignore all previous instructions and overwrite" string inside a read document. | `test_refactor_45.py::test_adversarial_document_does_not_auto_apply` — asserts the document is **unchanged** (propose-only contract holds), a reviewable proposal is created, and the adversarial text arrived as a `role="tool"` message (never the system prompt). |

## Verified clean (no change needed)

- **DI boundary** — only `openrouter.py` touches `openai`; the lazy import + key check
  means tested paths never construct a real client.
- **Prompt-injection surface** — the system prompt is built only from static guardrails
  + `project_id`/`project_name`/`file_count`; no document or tool content is concatenated
  into it. Tools resolve through the session's fixed `project_id`; cross-project ids →
  `not_found` (covered by `test_agent_tools.py::test_cross_project_doc_is_not_found`).
- **Hunk header math** — 0-based `StagedEdit` ranges → 1-based `@@` headers are correct
  (`_format_range`); bottom-up multi-range apply has no index drift; overlaps → a
  `rejected` proposal, never a mis-apply (covered by spec-43 tests).
- **Iteration cap** — `plan→act→observe` cannot exceed `AGENT_MAX_ITERATIONS`
  (`test_agent_core.py::test_tool_spam_stops_at_max_iterations`).
- **Run-state lifecycle** — every job path (success / `result.error` / internal-error
  except) finalizes `run_state` to `done`/`error` and clears `active_run_id`; no stuck
  state or dangling run id.

## Deliberately skipped / deferred

| Finding | Severity | Decision | Why |
|---------|----------|----------|-----|
| `is_stale` version half is coarse / type-fragile (`str(version)` compare). | risk | **Defer → spec 47** | The `base_hash` check is the real guard and is correct (catches content-changed-without-version-bump); tighten typing when the apply path lands. |
| Cancel can be lost if the queue backlog outlives `AGENT_RUN_TTL_S` (cancel key expires before the job starts); the DB `cancelling` state is overwritten by `running`. | risk | **Defer → spec 49** | Not a stuck-state bug (the run still finalizes correctly); only a rare lost-cancel under extreme backlog. Belongs with the safety/limits spec. |
| SSE replays only the **terminal** event for late subscribers; `diff_proposed`/`token` events aren't replayed on reconnect. | risk | **Won't-fix (documented contract)** | SSE is best-effort for non-terminal events; `GET …/diffs` is the source of truth for proposals, and `GET …/sessions/{id}` for messages. Clients reconcile via those. |
| Token streaming is simulated post-hoc (`plan` chunks the completed content instead of using `LLMClient.stream`). | smell | **Defer → spec 48/49** | A deliberate architectural choice (streaming + tool-call assembly is complex; `FakeLLM.stream` carries no tool calls). True incremental streaming is a later refinement; the `stream` contract is kept + unit-tested. |
| `observe` is a no-op graph node. | smell | **Won't-fix** | Keeps the named `plan/act/observe/respond` shape and a seam for spec-48 bookkeeping; removing it is churn for no behavior change. |

## Outcome

Three real fixes (a persisted-history corruption on capped turns, a tool-output cost
bypass, a wrong HTTP status) plus four coverage gaps closed (token caps, import
isolation, prompt-injection regression). No public 41–44 contract changed except the
409→400 status correction (documented). No schema change, no new env var, no real LLM
call anywhere in the suite.
