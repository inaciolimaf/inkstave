# Agent

The AI writing agent. A project member chats with it in the editor; it reads and searches the project,
looks at images, then proposes per-file diffs that the user reviews hunk by hunk, and file operations
(create, delete, rename, move) that the user applies or rejects. The turn runs server-side as a LangGraph
graph inside an ARQ job and streams to the browser over SSE. The agent never changes a project by itself:
a document edit is written in the browser after the user confirms, through the normal collaboration
channel, and a file operation runs in the backend only from the user's own apply request. Specs 41–50, 67
and 108; decision in `docs/adr/0110-agent-file-operations.md`.

## Where it is

| File | Role |
|---|---|
| `backend/src/inkstave/modules/agent` | Module root |
| `backend/src/inkstave/modules/agent/routes.py`, `backend/src/inkstave/modules/agent/schemas.py` | HTTP routes and their models |
| `backend/src/inkstave/modules/agent/access.py` | `require_member`, `owned_session`, shared by the route modules |
| `backend/src/inkstave/modules/agent/models.py` | `AgentSession`, `AgentMessage`, `AgentRunState` |
| `backend/src/inkstave/modules/agent/deps.py` | FastAPI dependencies; only `get_agent_enqueuer` is in use |
| `backend/src/inkstave/modules/agent/graph/builder.py` | `build_graph`: plan, act, observe, respond |
| `backend/src/inkstave/modules/agent/graph/nodes.py` | Node functions, tool dispatch, sentinels |
| `backend/src/inkstave/modules/agent/graph/runner.py` | `run_turn`: one turn, one transaction |
| `backend/src/inkstave/modules/agent/graph/state.py`, `backend/src/inkstave/modules/agent/graph/edits.py` | `AgentState`, `StagedEdit`, `EditMode` |
| `backend/src/inkstave/modules/agent/graph/prompts.py`, `backend/src/inkstave/modules/agent/graph/agent_deps.py`, `backend/src/inkstave/modules/agent/graph/repository.py` | System prompt, injected `AgentDeps`, session and message queries |
| `backend/src/inkstave/modules/agent/llm/base.py` | `LLMClient` protocol, message types, `LLMError` |
| `backend/src/inkstave/modules/agent/llm/anthropic_client.py` | `AnthropicLLMClient`, the default and the only `anthropic` import |
| `backend/src/inkstave/modules/agent/llm/openrouter.py` | `OpenRouterLLMClient`, the only `openai` import |
| `backend/src/inkstave/modules/agent/llm/factory.py` | `build_llm_client`, picks the client from `AGENT_LLM_PROVIDER` |
| `backend/src/inkstave/modules/agent/llm/stub.py`, `backend/src/inkstave/modules/agent/llm/fake.py` | `StubAgentLLM` for e2e, scripted `FakeLLM` for tests |
| `backend/src/inkstave/modules/agent/tools/base.py` | `Tool`, `ToolContext`, `ToolResult`, `ToolRegistry`, `authorize` |
| `backend/src/inkstave/modules/agent/tools/propose_edit.py` | `propose_edit`: stages, never applies |
| `backend/src/inkstave/modules/agent/tools/search_project.py`, `backend/src/inkstave/modules/agent/tools/read_file.py`, `backend/src/inkstave/modules/agent/tools/list_tree.py`, `backend/src/inkstave/modules/agent/tools/locate_section.py` | The read tools |
| `backend/src/inkstave/modules/agent/tools/files/view_image.py` | `view_image`: hands an image to the model |
| `backend/src/inkstave/modules/agent/tools/files/propose.py` | `propose_create`, `propose_delete`, `propose_move`: stage, never apply |
| `backend/src/inkstave/modules/agent/file_ops/__init__.py`, `backend/src/inkstave/modules/agent/file_ops/models.py`, `backend/src/inkstave/modules/agent/file_ops/repository.py` | `materialize_file_ops`, `ProposedFileOp`, queries |
| `backend/src/inkstave/modules/agent/file_ops/apply.py`, `backend/src/inkstave/modules/agent/file_ops/routes.py`, `backend/src/inkstave/modules/agent/file_ops/schemas.py`, `backend/src/inkstave/modules/agent/file_ops/paths.py` | Carrying out a proposal, its routes and models, pure path helpers |
| `backend/src/inkstave/modules/agent/tools/_latex.py` | Regex heading scan, used only for `search_project` ranking |
| `backend/src/inkstave/modules/agent/context/parser.py`, `backend/src/inkstave/modules/agent/context/project_map.py` | `parse_latex_structure`, `build_project_map` |
| `backend/src/inkstave/modules/agent/context/locate.py`, `backend/src/inkstave/modules/agent/context/select.py` | `locate_section`; `select_context`, not wired to the turn |
| `backend/src/inkstave/modules/agent/diffs/__init__.py`, `backend/src/inkstave/modules/agent/diffs/compute.py` | `materialize_diffs`, `is_stale`; pure diff computation |
| `backend/src/inkstave/modules/agent/diffs/models.py`, `backend/src/inkstave/modules/agent/diffs/repository.py` | `ProposedDiff`, `ProposedDiffStatus`, queries |
| `backend/src/inkstave/modules/agent/runs/jobs.py`, `backend/src/inkstave/modules/agent/runs/run_helpers.py` | `run_agent_turn`; `RunScope`, pre-checks, terminal event |
| `backend/src/inkstave/modules/agent/runs/enqueuer.py`, `backend/src/inkstave/modules/agent/runs/events.py`, `backend/src/inkstave/modules/agent/runs/stream.py` | `AgentEnqueuer`; Redis keys and sinks; `sse_stream` |
| `backend/src/inkstave/modules/agent/runs/cleanup.py` | `agent_audit_cleanup` cron |
| `backend/src/inkstave/modules/agent/safety/rate_limit.py`, `backend/src/inkstave/modules/agent/safety/budget.py` | Limits and budgets |
| `backend/src/inkstave/modules/agent/safety/injection.py`, `backend/src/inkstave/modules/agent/safety/audit.py`, `backend/src/inkstave/modules/agent/safety/models.py` | `wrap_untrusted`, `flag_injection`; `audit`; `AgentAuditLog` |
| `backend/src/inkstave/core/config/agent.py` | `AgentSettings` |
| `backend/src/inkstave/worker.py` | Registers the job and the cron, picks the stub LLM |
| `frontend/src/modules/agent/useAgentChat.ts`, `frontend/src/modules/agent/reducer.ts` | Sessions, runs, `EventSource`, transcript |
| `frontend/src/modules/agent/file-op-card.tsx` | The card that applies or rejects a file operation |
| `frontend/src/modules/diff-review/useDiffReview.ts`, `frontend/src/modules/diff-review/hunks.ts` | Hunk decisions, drift, `rebaseHunks` |
| `frontend/src/modules/diff-review/editor-bridge.ts`, `frontend/src/modules/diff-review/crdt-apply.ts` | Writes through a short-lived collab provider |
| `backend/tests/agent_evals/test_agent_evals.py` | Deterministic eval suite, `FakeLLM` only |
| `backend/tests/unit/test_agent_egress_lock.py` | Static guard: tools import no network client |

## Data

| Table | Migration | Content |
|---|---|---|
| `agent_sessions` | `backend/migrations/versions/20260610_1700_a7b9d3e35f68_create_agent_tables.py` | Chat per project and user: `title`, `status`, `model` |
| `agent_messages` | same | Transcript. `seq` is unique per session. System prompt is never stored |
| `agent_sessions.run_state`, `active_run_id` | `backend/migrations/versions/20260610_2100_c9d2e6f58b71_agent_session_run_state.py` | `idle`, `queued`, `running`, `cancelling`, `done`, `error` |
| `proposed_diffs` | `backend/migrations/versions/20260610_1900_b8c1d5f47a69_create_proposed_diffs.py` | One proposal per document: `base_version`, `base_hash`, `diff_text`, `hunks`, `stats`, `status`, `rationale` |
| `proposed_file_ops` | `backend/migrations/versions/20261102_2000_c5e9a1b37d42_create_proposed_file_ops.py` | One proposal: `kind`, `entity_type`, `entity_id`, `path`, `new_path`, `content`, `affected_paths`, `status`, `rationale` |
| `agent_audit_log` | `backend/migrations/versions/20260610_2300_d1e3f7a69c82_create_agent_audit_log.py` | Action rows with tokens and cost, no document bodies |

`stats` is `{additions, deletions, hunk_count}`. `session_id` and `run_id` in `agent_audit_log` are plain
columns with no foreign key, so audit rows outlive their session.

Redis, all short-lived: `agent:run:{run_id}` (pub/sub channel), `agent:run:{run_id}:last` (terminal event)
and `agent:cancel:{run_id}` (cancel flag), both for `AGENT_RUN_TTL_S`; `agent:rl:user:{id}:{minute}` and
`agent:rl:proj:{id}:{minute}` (runs per minute, 120 s); `agent:conc:user:{id}` (in flight, 3600 s);
`agent:day:proj:{id}:{day}:tokens` and `agent:day:user:{id}:{day}:microusd` (per UTC day, 2 days).

`build_project_map` also keeps a process-local dict `_CACHE`, keyed by project and content hash. It is
unbounded.

## Routes

All under `/api/v1/projects/{project_id}/agent`. Every route runs `_require_member` first: 404
`project_not_found` for a missing or deleted project, 403 `not_project_member` for an
outsider. Any role passes, viewers included. A session that belongs to another user, or to another
project, is a 404.

| Method and path | What it does | Errors |
|---|---|---|
| `POST /sessions` | Create a session, 201. `model` is the current `AGENT_MODEL` | `not_project_member` |
| `GET /sessions` | The caller's sessions, newest first. `limit` 1–100, default 50 | `not_project_member` |
| `GET /sessions/{session_id}` | Session, messages, and `proposed` diffs without hunks | `not_project_member` |
| `POST /sessions/{session_id}/messages` | Start a run, 202 with `run_id` and `stream_url`. Named rate limit `agent` | 400 `message_too_long` with `details: [{max_chars}]`, 409 `run_active` |
| `POST /sessions/{session_id}/runs/{run_id}/cancel` | Set the cancel flag, 202 | `not_project_member` |
| `GET /sessions/{session_id}/runs/{run_id}/events` | SSE stream. Token in the header or in `?access_token=` | 401 when no valid token, `not_project_member` |
| `GET /sessions/{session_id}/diffs` | All the session's diffs. `?status=` filters, `?include=hunks` adds hunks | 422 on an unknown status |
| `GET /sessions/{session_id}/file-ops` | The session's file operations with `content`, without superseded ones | `not_project_member` |
| `POST /sessions/{session_id}/file-ops/{op_id}/apply` | Carry out one proposal and audit `apply_recorded`. Needs `DOC_WRITE` now | 403 `file_op_forbidden`, 404 `file_op_not_found`, 409 `file_op_closed`, `file_op_stale`, and the tree's own errors |
| `POST /sessions/{session_id}/file-ops/{op_id}/reject` | Record the refusal | same as apply, without the tree's |

There is no route to apply, accept or reject a diff.

SSE events are named after their `type` and carry `run_id`, `seq`, `ts`: `token` (`text`), `tool_call`
(`tool_call_id`, `name`, `arguments`), `tool_result` (`tool_call_id`, `name`, `ok`, `summary`),
`diff_proposed` (`diff_id`, `doc_id`, `path`, `stats`), `file_op_proposed` (`file_op_id`, `kind`,
`entity_type`, `path`, `new_path`, `affected_paths`, `rationale`), `done` (`usage`, `iterations`, `final_text`),
`error` (`code`, `message`, and `retry_after` when rate limited). `done` and `error` are terminal. Error
codes are `agent_rate_limited`, `agent_budget_exceeded`, `cancelled`, `internal`, `timeout`, `not_found`.
Keep-alives are `: ping` comments.

## How it works

### One turn

1. `post_message` checks membership, ownership, `AGENT_MAX_MESSAGE_CHARS` and `run_state`. It sets
   `queued` and a new `active_run_id`, runs `flush_open_project_docs` so open CRDT rooms reach
   `documents.content`, then calls `AgentEnqueuer.enqueue`. The browser pushes pending local edits first
   (`onBeforeSend` in `frontend/src/modules/agent/useAgentChat.ts`). On `message_too_long` the panel names
   the limit, drops the message from the transcript and puts the draft back in the composer.
   Any other 4xx at this step shows under its error type, and a 5xx or network failure as `internal`.
2. The browser opens `EventSource` on `stream_url`. `sse_stream` subscribes before it looks for a stored
   terminal event, so it cannot miss one.
3. The worker runs `run_agent_turn`, which binds log context and calls `_run_agent_turn`. That resolves
   settings, the sink and the LLM, then `_run_scoped` runs `precheck_run` (rate limit, then day budget).
   A block emits a terminal `error`, audits and sets `run_state` to `error`.
4. `acquire_run` counts the run. `_execute_turn` commits `running`, audits `run_start`, builds `AgentDeps`
   and calls `run_turn`.
5. `run_turn` raises the idle-in-transaction limit with `allow_idle`, builds the transcript (fresh system
   prompt, stored history, new message), inserts the user message and runs the graph.
6. Back in `run_turn`, the messages the turn produced are stored, and `materialize_diffs` turns staged
   edits into `proposed_diffs` rows. This happens on every ending, including a cancelled or over-budget
   turn, so edits staged before the stop are kept.
7. `persist_results` writes tool audit rows, emits `diff_proposed` and audits `proposal_created` for each
   diff, and records usage. `emit_terminal` emits `done` or `error`. Then `run_stop` is audited, `run_state`
   is set, `active_run_id` is cleared and the transaction commits. `release_run` frees the slot.

The turn is one transaction from step 5 to step 7, so a failed turn leaves no messages or diffs.
`_settle_error` rolls back, emits a terminal error, sets `run_state` to `error` and audits. An exception
becomes code `internal`; `asyncio.CancelledError` from ARQ's timeout becomes code `timeout`, settled under
`asyncio.shield` and re-raised. Raw error strings are logged, never sent to the client.

### The graph

`START → plan → (act → observe → plan)* → respond → END`. `route_after_plan` leaves the loop for `respond`
when there is an error, no pending tool call, `iterations >= AGENT_MAX_ITERATIONS`, or
`total_tokens >= AGENT_MAX_TOTAL_TOKENS`.

- `plan` checks the cancel flag and the per-run budget, frames tool messages when the guard is on, and
  makes one `complete()` call. Prose is split into 16-character `token` events afterwards: nothing streams
  from the provider, by choice, because `tool_calls` and `usage` need the full response (`_complete`
  documents it, `LLMClient.stream` is unused in the turn).
- `act` checks the cancel flag (cancel is cooperative: a request in flight runs to its end) and runs each pending call through `_dispatch_call`, which emits and audits
  `tool_call` and `tool_result`, and flags injection patterns. Tool failures become `ToolResult` errors the
  model reads; they never raise.
- `observe` is an empty placeholder.
- `respond` writes the closing text. Errors map to fixed text in `_ERROR_CLOSINGS`. A turn capped with work
  still queued streams `_CAPPED_NOTE`, so a partial result reads as partial; the run still ends in `done`.

### LLM client

Nodes see only the `LLMClient` protocol through `AgentDeps.llm`. `_resolve_llm` takes `ctx["llm_client"]`
when set and otherwise calls `build_llm_client`, so changing provider is a settings change.
`AGENT_LLM_PROVIDER=anthropic`, the default, builds `AnthropicLLMClient`, which needs only
`ANTHROPIC_API_KEY` and runs `claude-haiku-5-5`. `openrouter` builds `OpenRouterLLMClient`, an `AsyncOpenAI`
with `OPENROUTER_BASE_URL` that needs `OPENROUTER_API_KEY` and a matching `AGENT_MODEL`. With `LLM_STUB=true`
the worker sets `ctx["llm_client"]` to `StubAgentLLM`, which walks `search_project`, `read_file`,
`propose_edit`, then a fixed reply, deriving its step from the count of tool messages.

`_parse_tool_calls` keeps a malformed call as `{"_raw": ...}` and sets `finish_reason="error"`. `_run_tool`
then fails validation and the model sees `invalid_args`. A response with `finish_reason="tool_calls"` and no
parsed call also becomes `"error"`, and with no call to run `plan` ends the turn with `TOOL_CALL_UNPARSED`.

`AnthropicLLMClient` differs in four ways. `complete` streams and returns the final message, since one call
can write a whole document. It sends no `temperature`, which Claude Haiku 5.5 rejects, so `AGENT_TEMPERATURE`
applies only to OpenRouter. The model thinks by default, and thinking blocks must go back unchanged with the
tool results, so `provider_blocks` carries the assistant turn through the graph's state; it is not persisted,
so later turns replay only text and tool calls. A tool call cut by `max_tokens` becomes `"error"` with no call,
and a `refusal` raises `LLMError`.

### Tools

`default_registry` holds exactly nine. Each calls `authorize`, which re-reads the role on every call, and is
scoped to `ToolContext.project_id`.

| Tool | Does | Limit |
|---|---|---|
| `search_project` | Case-insensitive keyword over text docs and paths. Ranks section, content, path | `AGENT_TOOL_SEARCH_MAX_RESULTS`, 240-char snippets, 8192-char soft payload cap |
| `read_file` | Reads by `doc_id` or `path`, with an optional line window | `AGENT_TOOL_READ_MAX_CHARS` |
| `list_tree` | Tree under a path, depth 1–10 | `AGENT_TOOL_TREE_MAX_NODES` |
| `locate_section` | Resolves a human section name through the structure parser | Name up to 120 chars |
| `propose_edit` | Stages a `StagedEdit`. `require_write=True`, so viewers get `forbidden` | `AGENT_TOOL_EDIT_MAX_CHARS` |
| `view_image` | Hands a PNG, JPEG, GIF or WebP to the model. The type comes from the bytes | `AGENT_TOOL_IMAGE_MAX_BYTES` |
| `propose_create` | Stages a new document with its whole text, or a folder. Missing folders on the path are created on apply. `require_write=True` | `AGENT_TOOL_EDIT_MAX_CHARS` |
| `propose_delete` | Stages a delete and records what it removes in `affected_paths`. `require_write=True` | — |
| `propose_move` | Stages a rename, a move or both. `require_write=True` | — |

A foreign or malformed id is `not_found`, a binary file is `unsupported`. `mode` is `full` or `range`
(0-based, end exclusive). The tools added by spec 108 accept a path with a leading `/` or `./`; the older
read tools still want it exactly as the tree spells it.

### Images

`ToolResult.images` and `LLMMessage.images` carry `LLMImage` beside the JSON result, and both fields are
excluded from every dump, so an image reaches neither `agent_messages`, the audit log nor the stream. It is
sent again on each model call of that turn and is gone in the next one. `AnthropicLLMClient` puts it inside
the `tool_result` block. OpenAI tool messages hold only text, so `OpenRouterLLMClient` sends it as a user
message after the turn's last tool result, and needs an `AGENT_MODEL` with vision.

### File operations

1. A tool validates the path against the current tree and appends a `StagedFileOp` to
   `ToolContext.staged_file_ops`. Two proposals on one path in a turn are refused. Nothing changes.
2. At the end of the turn `materialize_file_ops` stores one `proposed_file_ops` row each, moving an open row
   for the same session and path to `superseded`. Like diffs, this happens on a cancelled or capped turn.
3. `file_op_proposed` tells the panel, and `GET /sessions/{session_id}` brings them back on reload, without
   `content`, which the card loads on demand.
4. The user applies or rejects on `FileOpCard`. A delete asks for confirmation.
5. `apply_file_op` runs in the request's transaction, so a failure leaves nothing. A delete or move is
   refused as `file_op_stale` if the target is no longer at `path`, and a delete also if its subtree no longer
   matches `affected_paths`: the user approved that list. A refused proposal stays open.
6. The card refreshes the tree, and `useSelectionFollowsTree` in
   `frontend/src/modules/editor/selection-follows-tree.ts` keeps the open file right: it clears a removed
   file and follows a renamed or moved one.

### Context and section parsing

`parse_latex_structure` is one line-by-line pass. It strips comments, treats verbatim environments as
opaque, records sectioning commands, notable environments, `\input`, `\include`, `\subfile` and `\label`,
and never raises on malformed input. Line numbers in `StructureNode` are 1-based, unlike the tools' 0-based
windows. `build_project_map` parses every doc, picks the first with `\documentclass` as main, and splices
included outlines, with a cycle guard and a list of unresolved inputs.

`locate_section` scores by exact title (1.0), label (0.95), ordinal such as "section 2" (0.92), synonym
(0.9), substring (0.7), token overlap (up to 0.6). An ordinal match returns alone.

`select_context` builds a `ContextBundle` within a token budget: target section with surrounding lines
first, then an outline, then up to three related matches, truncating or dropping what does not fit. Tokens
are estimated at four characters each. It is tested but nothing in the turn calls it.

### How a proposed edit reaches the user

1. The model calls `propose_edit`. The tool validates and appends a `StagedEdit` to
   `ToolContext.staged_edits`. The document is untouched and the result says `staged: true`.
2. At the end of the turn `materialize_diffs` groups edits by document and re-reads each one. It skips a
   missing document, one over `AGENT_DIFF_MAX_DOC_CHARS`, and a no-op.
3. `apply_staged_edits` builds the proposed text in memory. `full` wins over `range`, with a note in the
   rationale. Overlapping ranges raise `DiffConflictError` and store a `rejected` row with no hunks.
4. `compute_diff` uses `difflib` over lines and returns `diff_text`, hunks `h1`, `h2`… and `stats`.
5. `_persist` moves earlier `proposed` rows for the same session and document to `superseded`, then inserts
   the new one with `base_version` and `base_hash`.
6. `diff_proposed` tells the panel. Reloading uses `GET /sessions/{session_id}`.
7. The review dialog fetches `?include=hunks`. `useDiffReview` starts with every hunk accepted and compares
   hunks to live text. `rebaseHunks` locates each hunk by its old lines, searching outward from the original
   position, and blocks those no longer found. Drift is judged from content, not from `base_version`.
8. On confirmation, `bridge.applyContent` writes the result into the document's Yjs text in one transaction
   with origin `agent-apply`, as a single minimal region, so concurrent edits elsewhere survive. The write
   reaches the server as an ordinary collaboration update from that user.

### Worker wiring

`startup` puts `AgentSettings` in `ctx["agent_settings"]`, separate from `ctx["settings"]`. `WorkerSettings`
registers `run_agent_turn` with `max_tries=1` and `timeout=agent_job_timeout_s`, and `agent_audit_cleanup`
both as a function and as a cron at 03:30. Agent jobs share the compile queue: the enqueuer and
`WorkerSettings.queue_name` both use `compile_queue_name`.

## Rules and guarantees

| Invariant | Test |
|---|---|
| A turn with a proposal leaves the document unchanged | `backend/tests/agent_evals/test_agent_evals.py::test_eval_never_auto_applies` |
| `propose_edit` stages without changing the document | `backend/tests/integration/test_agent_tools_authz.py::test_propose_edit_stages_without_changing_doc` |
| Viewers can read but not propose | `backend/tests/integration/test_agent_tools_authz.py::test_viewer_cannot_propose_but_can_read` |
| A document from another project is `not_found` | `backend/tests/integration/test_agent_tools_authz.py::test_cross_project_doc_is_not_found` |
| Only `openrouter.py` imports `openai` | `backend/tests/unit/test_agent_core.py::test_only_openrouter_imports_openai` |
| Only `anthropic_client.py` imports `anthropic` | `backend/tests/unit/test_agent_core.py::test_only_the_anthropic_client_imports_anthropic` |
| `AnthropicLLMClient` defaults to Haiku 5.5, sends no sampling parameter and replays thinking | `backend/tests/unit/test_anthropic_adapter.py` |
| No tool module imports a network client | `backend/tests/unit/test_agent_egress_lock.py::test_no_agent_tool_module_imports_a_network_client` |
| A tool outside the registry never runs and is flagged | `backend/tests/agent_evals/test_agent_evals.py::test_eval_disallowed_tool_is_flagged` |
| Injection-shaped document text is flagged and the document kept | `backend/tests/agent_evals/test_agent_evals.py::test_eval_injection_does_not_change_behaviour` |
| A proposal changes nothing until the user applies it | `backend/tests/integration/test_agent_file_ops.py::test_a_proposal_changes_nothing_until_the_user_applies` |
| Applying needs write access at that moment | `backend/tests/integration/test_agent_file_ops.py::test_a_viewer_cannot_apply` |
| A folder that changed since the proposal is not deleted | `backend/tests/integration/test_agent_file_ops.py::test_delete_is_refused_when_the_folder_gained_a_file` |
| A decided proposal cannot run twice | `backend/tests/integration/test_agent_file_ops.py::test_delete_and_move_apply_and_cannot_apply_twice` |
| The model gets an image and the transcript does not keep it | `backend/tests/integration/test_agent_view_image.py::test_the_model_gets_the_image_and_the_transcript_does_not` |
| A second message during a run is refused, one after a terminal state is accepted | `backend/tests/integration/test_agent_api.py::test_post_message_enqueues_and_conflicts`, `backend/tests/integration/test_agent_api.py::test_post_message_after_terminal_state_starts_new_run` |
| Rate-limited run is refused before the LLM | `backend/tests/integration/test_agent_safety_api.py::test_rate_limited_run_is_refused` |
| Exhausted day budget refuses the run | `backend/tests/integration/test_agent_safety_api.py::test_day_budget_preflight_refusal` |
| An over-budget step never runs and the sentinel stays out of the transcript | `backend/tests/integration/test_agent_safety_api.py::test_midrun_budget_stops_over_budget_step` |
| A run has audit rows, without document bodies | `backend/tests/integration/test_agent_safety_api.py::test_audit_rows_for_a_full_run` |
| A cancelled run ends in `error` with code `cancelled` | `backend/tests/integration/test_agent_api_streaming.py::test_cancellation` |
| SSE requires auth and membership at connect | `backend/tests/integration/test_agent_api_sse.py::test_sse_events_route_requires_auth` |
| A revoked session cannot open a new SSE stream | `backend/tests/integration/test_session_revocation.py::test_websocket_and_sse_paths_refuse_a_revoked_session` |
| A new proposal supersedes the old one for the same document | `backend/tests/integration/test_agent_diffs.py::test_superseding_prior_proposal` |
| Overlapping ranges are rejected, never mis-applied | `backend/tests/integration/test_agent_diffs.py::test_overlapping_ranges_rejected` |
| Oversized documents and no-ops create no row | `backend/tests/integration/test_agent_diffs.py::test_oversized_doc_is_skipped`, `backend/tests/integration/test_agent_diffs.py::test_noop_edit_creates_no_row` |
| The turn raises its idle limit first | `backend/tests/unit/test_external_timeouts.py::test_the_agent_turn_raises_its_idle_limit_first` |
| A timed-out job settles as `timeout` | no dedicated test |
| `?include=hunks` controls whether hunks are sent | no dedicated test |
| An open SSE stream ends on revocation | not a guarantee: it does not (see below) |

`backend/tests/agent_evals/test_agent_evals.py` runs in the normal fast suite with `FakeLLM` and the
integration marker. It calls no real model, so it pins invariants, not model quality.

## Settings

Defaults are from `backend/src/inkstave/core/config/agent.py`, and `.env.example` matches them.

| Group | Variables |
|---|---|
| Provider | `AGENT_LLM_PROVIDER` `anthropic`; `ANTHROPIC_API_KEY` empty, needed when the real client is built; `AGENT_MODEL` `claude-haiku-5-5`; `OPENROUTER_API_KEY` empty, needed with `openrouter`; `OPENROUTER_BASE_URL` `https://openrouter.ai/api/v1`; `AGENT_TEMPERATURE` 0.2, OpenRouter only; `AGENT_HTTP_REFERER` `https://inkstave.local`; `AGENT_APP_TITLE` `Inkstave` |
| Turn | `AGENT_MAX_TOKENS_PER_CALL` 32000, too small truncates a `propose_edit`; `AGENT_REQUEST_TIMEOUT_S` 120, per SDK call; `AGENT_JOB_TIMEOUT_S` 600, whole turn; `AGENT_MAX_ITERATIONS` 15; `AGENT_MAX_TOTAL_TOKENS` 60000, soft cap, run still `done`; `AGENT_MAX_MESSAGE_CHARS` 40000 |
| Tools | `AGENT_TOOL_READ_MAX_CHARS` 40000; `AGENT_TOOL_SEARCH_MAX_RESULTS` 50; `AGENT_TOOL_TREE_MAX_NODES` 500; `AGENT_TOOL_EDIT_MAX_CHARS` 200000; `AGENT_TOOL_IMAGE_MAX_BYTES` 3750000 |
| Diffs | `AGENT_DIFF_CONTEXT_LINES` 3; `AGENT_DIFF_MAX_DOC_CHARS` 400000 |
| Stream | `AGENT_STREAM_HEARTBEAT_S` 15; `AGENT_RUN_TTL_S` 900; `AGENT_STREAM_TRANSPORT` `sse`, unused |
| Context | `AGENT_CONTEXT_CACHE` `memory`, and `redis` behaves like `off`; `AGENT_SECTION_EXTRA_COMMANDS` empty; `AGENT_CONTEXT_TOKEN_BUDGET` 8000 and `AGENT_CONTEXT_SURROUNDING_LINES` 40, both unused |
| Limits, 0 disables | `AGENT_MAX_RUNS_PER_MINUTE_PER_USER` 10; `AGENT_MAX_CONCURRENT_RUNS_PER_USER` 2; `AGENT_MAX_RUNS_PER_MINUTE_PER_PROJECT` 20 |
| Budgets, 0 disables | `AGENT_MAX_TOKENS_PER_RUN` 120000; `AGENT_MAX_COST_PER_RUN_USD` 0.30; `AGENT_MAX_TOKENS_PER_DAY_PER_PROJECT` 2000000; `AGENT_MAX_COST_PER_DAY_PER_USER_USD` 0.30 |
| Safety | `AGENT_MODEL_COST_TABLE` Claude Haiku 5.5 rates first (they price any model not listed), then gpt-4o-mini, USD per 1K tokens; `AGENT_AUDIT_RETENTION_DAYS` 90, 0 keeps forever; `AGENT_INJECTION_GUARD` `on` |

Elsewhere: `RATE_LIMIT_AGENT` (`30/60`, per user, HTTP layer of `POST .../messages`), `LLM_STUB` (false),
`VITE_AGENT_ENABLED` (shows the panel).

## Points of attention

**The backend does not know which diffs were applied.** Only file operations record an outcome. `set_status` is never called, so `applied`, `partially_applied` and `stale` are never set, and `apply_recorded` is never written. An applied proposal stays `proposed` until a later proposal for the same session and document supersedes it, so `GET /sessions/{session_id}` keeps returning it after a reload. `rejected` comes only from overlapping ranges. `is_stale` is used only by its test.

**Timeouts.** `AGENT_REQUEST_TIMEOUT_S` bounds one LLM request. `AGENT_JOB_TIMEOUT_S` is the ARQ `timeout` for the whole turn, and `run_turn` passes the same value to `allow_idle`, because the transaction stays open across model calls. Fifteen plan steps at 120 s exceed 600 s, and the SDK's default two retries are not disabled, so one call can take three times the request timeout. The job timeout is the real ceiling and a slow multi-step turn can hit it.

**The per-run token cap is unreachable with defaults.** `route_after_plan` stops at 60000 and the budget check runs at the start of `plan`, which is reached only through that router, so 120000 never fires. The cost cap is out of reach too at the default rates. They bite only when set below the soft cap, as the tests do. `AgentDeps.run_token_budget`, `run_cost_budget_usd` and `cost_per_1k` are set and never read; `_budget_exceeded` reads settings directly.

**Day counters miss failed runs.** `record_usage` runs in `persist_results`, so a timed-out or crashed turn adds nothing, though the provider billed it. An unknown model is priced with the first table entry.

**Runs can wedge.** Nothing resets `run_state`. `_resolve_llm` and `precheck_run` run outside any `try`, and the comment in `_run_scoped` says `acquire_run` is inside the `try` when it is before it. A missing `OPENROUTER_API_KEY`, or Redis failing there, fails the job with no terminal event: the session stays `queued`, each new message gets 409 `run_active`, and the SSE stream pings until the client leaves. So does a worker killed mid-turn, which also holds a concurrency slot for up to an hour. The key is checked only by the production config check in `backend/src/inkstave/modules/admin/provisioning/config_check.py`.

**Open SSE streams survive revocation.** `sse_user` runs once, at connect. `sse_stream` reads Redis until a terminal event and never re-checks the token, session or membership. Logout, deactivation or removal from the project does not close an open stream, and the run goes on: only tools re-check, through `authorize`.

**`run_id` is not tied to the session.** `run_events` and `cancel_run` verify the session, not that `run_id` belongs to it, and `cancel_run` sets the flag before comparing `active_run_id`. Holding some other run's UUID is enough to read or cancel it. UUIDs are unguessable, so this is defence in depth.

**Events go out before the commit.** `diff_proposed` and `done` are published before the final commit. A client acting on them instantly can miss the row or get 409. A commit failure after `done` produces a second terminal event.

**`hunks` and `stats` are separate.** `_diff_summary` in `backend/src/inkstave/modules/agent/routes.py` clears `hunks` unless asked. Commit b83e563 corrected it: `model_validate` already filled `hunks`, so the flag did nothing and lists always carried them. It changed what is sent, not how hunks are counted; `hunk_count` comes from `_stats` in `backend/src/inkstave/modules/agent/diffs/compute.py`. No test calls it directly or asserts on `hunks` in a response. `test_diff_proposed_event_and_listing` goes through it without looking at that field.

**Edits and drift.** `StagedEdit.base_version` is recorded and never compared. `propose_edit` checks range bounds at stage time, but ranges apply to the text re-read at the end of the turn, so collaborator edits during the turn can shift them. `diff_proposed` also fires for a `rejected` row, with zero hunks, and that row still supersedes the previous proposal.

**Replayed tool calls.** A capped or cancelled turn can store an assistant message with `tool_calls` and no tool result, and the next turn replays it. OpenAI-style APIs may reject that; not verified against a provider.

**Unused code.** `select_context`, `AGENT_CONTEXT_TOKEN_BUDGET` and `AGENT_CONTEXT_SURROUNDING_LINES`: the model gets no pre-selected context and must call tools. Also `AGENT_STREAM_TRANSPORT`, `get_llm_client`, `get_agent_deps`, `list_open_for_project`, `ProposedDiffOut`, `section_range`, `match_score`, `serialize_state` outside its test. `AGENT_SECTION_EXTRA_COMMANDS` reaches the parser, but `_TOKEN_RE` lists fixed commands, so extra names produce no nodes. `PromptContext` is built with `project_id` only.

**Injection guard limits.** `flag_injection` only audits, it blocks nothing. `wrap_untrusted` frames tool messages sent to the model and the transcript stays raw. Protection against acting on injected text rests on every tool only proposing and on review by the user. Text inside an image is not scanned at all.
