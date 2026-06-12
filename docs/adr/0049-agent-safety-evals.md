# ADR 0049 — Agent safety: limits, budgets, injection guard, audit, evals

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 49 — Agent Safety & Evals

## Context

The agent (specs 41–48) needs to be safe and verifiable before production: bounded in
rate and cost, resistant to prompt injection, fully audited, and covered by a
deterministic eval suite. All enforcement runs inside the existing spec-44 run job.

## Decisions

### 1. Redis-backed rate limits, checked at run start

`check_rate_limit` reads fixed per-minute windows (per user, per project) + a
per-user concurrency counter from Redis; a cap of `0` disables that check. On deny the
job emits `agent_rate_limited` (with `retry_after`), writes a `limit_block` audit row,
and **never calls the LLM**. `acquire_run`/`release_run` bracket the run for
concurrency. The clock is injected (`ctx["clock"]`) so tests are deterministic — no
sleeps for windows.

### 2. Two-layer token/cost budgets

`cost = tokens × AGENT_MODEL_COST_TABLE rate`. **Per-day** caps (project tokens, user
cost) are **pre-checked** at run start from Redis day rollups — exhausted → refuse
pre-flight with `agent_budget_exceeded`, no LLM call. **Per-run** caps
(`AGENT_MAX_TOKENS_PER_RUN`, `…_COST_PER_RUN_USD`) are a **mid-run checkpoint** at the
start of every `plan` node: if the accumulated total already crosses the cap, the node
returns a `budget_exceeded` sentinel **before making the over-budget LLM call**, the
run routes to `respond`, and the job emits `agent_budget_exceeded` + a `budget_block`
audit row. The run's usage is rolled into the Redis day counters afterwards.

### 3. Injection mitigation by framing, not trust

Untrusted content (tool results, document text) is **never** placed in the system or
developer role. Tool-role message content is wrapped in `<untrusted_tool_result>` blocks
**only at LLM-send time** (`_frame_for_llm` in `plan`) — the stored transcript keeps raw
JSON, so persistence and tooling are unaffected. The system prompt now asserts that
content in `<untrusted_…>` blocks is data, never instructions, and that system
instructions take precedence. A deterministic `flag_injection` heuristic (override
patterns) adds an `injection_flagged` audit entry — best-effort, never blocks edits. The
**capability guard** is structural: the agent can only call the spec-42 allow-list; any
unknown/disallowed tool is rejected (not run) and logged `injection_flagged`. Apply
stays user-only (spec 47) — the agent has no document-writing tool.

### 4. Audit log: structured, redacted, non-blocking

`agent_audit_log` (migration `d1e3f7a69c82`) records every lifecycle point
(`run_start`/`run_stop`/`tool_call`/`tool_result`/`proposal_created`/`limit_block`/
`budget_block`/`injection_flagged`/`error`) with token/cost fields and a JSONB `detail`
that holds **hashes/ids/counts, never full document bodies or secrets**. The act node
collects audit events onto the `ToolContext`; the job flushes them with the run's
ids/usage. `audit()` swallows its own failures (logged) so auditing never crashes a run.

### 5. Error codes shared with spec 46

The job emits `agent_rate_limited` (retryable, `retry_after`) and
`agent_budget_exceeded` (not retryable). Spec 46's reducer maps both to friendly
messages; a hit budget is non-retryable while a rate limit is.

### 6. A deterministic eval suite

`tests/agent_evals/` asserts the headline invariants with FakeLLM + fixtures (no
network): section-location accuracy (48), valid unified-diff proposals (43), budget
stop, injection-flagged-and-no-behaviour-change, and — the load-bearing guarantee —
**the agent never auto-applies** (a `propose_edit` turn leaves the document byte-for-byte
unchanged). It runs in the normal fast suite.

## Consequences

- New `inkstave.agent.safety` package + `agent_audit_log` table. Eleven new settings
  (all env-overridable; `0`/`off` disables a cap). `AgentDeps`/`ToolContext` gain
  safety fields; the run job is the single enforcement point. Frontend reducer maps the
  two new codes.
- 20 tests: safety units (rate/budget/injection/audit), job-path integration
  (rate/day-budget/mid-run-budget/audit-rows/injection-flag), and the 6-eval suite.
  Suite stays ~56s; FakeLLM + fakeredis + injected clock everywhere.
