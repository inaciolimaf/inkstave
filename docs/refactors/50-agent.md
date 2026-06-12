# Refactor 50 — Full AI Agent (specs 41–49)

A structured review of the entire agent feature. Analysis was fanned out across four
read-only reviewers (foundation+tools, diff-gen+review/apply, streaming+safety,
chat-UI+parser). Each finding below carries a severity and a **fix**/**skip** decision
with rationale; applied fixes are locked by a named test. No new features; all public
contracts preserved except the documented internal-error-message change (a security fix).

Suite after refactor: **backend 721 passed / 1 skipped (~57s)**, **frontend 321 passed**,
ruff + mypy (184 files) + eslint + tsc clean. The eval suite (`tests/agent_evals/`) stays
deterministic and green.

## Applied fixes

| # | Spec | File | Sev | Finding | Test |
|---|------|------|-----|---------|------|
| 1 | 44 | `agent/api/jobs.py` | **high** | `acquire_run` ran *outside* the `try/finally`; a failure during run setup (commit/audit/deps) leaked the per-user concurrency slot (1h TTL) and left the session stuck `running` with no terminal event. Moved acquire inside the guarded block so `release_run` + a terminal `error` always fire. | `test_internal_error_message_is_not_leaked` (exercises the failure path; slot released, terminal error streamed) |
| 2 | 44/49 | `agent/api/jobs.py` | **med (security)** | The generic-error branch streamed `message=result.error` — a raw `agent error: <exc>` / `LLM request failed: <exc>` string — leaking internal/provider detail to the browser. Now emits a fixed generic message and logs the detail server-side only. | `test_internal_error_message_is_not_leaked` |
| 3 | 41/44 | `agent/nodes.py` (`respond`) | **med** | On cancel/budget/error, the raw sentinel/exception string was written as the assistant message **and persisted** into the chat transcript (reappearing as history next turn). Now maps to neutral user-facing closing text; the raw string is never persisted. | `test_midrun_budget_stops_over_budget_step` (asserts persisted content) |
| 4 | 48 | `agent/context/parser.py` | **med** | Verbatim opacity was broken: `_strip_comment` ran *before* the verbatim check, so a literal `%` before an inline `\end{verbatim}` hid the close tag and swallowed the rest of the file. Verbatim lines are now scanned raw (no comment stripping). | `test_verbatim_percent_does_not_swallow_rest_of_file` |
| 5 | 48 | `agent/context/project_map.py` | low | `unresolved_inputs` accumulated duplicates when the same missing target was reached via several `\input` sites. Deduped (first-seen order). | `test_project_map_dedupes_unresolved_inputs` |
| 6 | 46 | `agent/transcript.tsx` | **med (a11y)** | `aria-live="polite"` on the whole log re-announced the entire growing message on every token (screen-reader flooding). The log is no longer a live region; a dedicated `role="status"` announcer carries only completed assistant messages / errors. | `transcript.test.tsx` "has a labelled log plus a polite announcer…" |
| 7 | 46 | `agent/reducer.ts` | **med** | A terminal `done`/`cancelled` did not clear a previously-set `error`, so the destructive error alert could persist after a run resolved. Both branches now clear `error`. | `reducer.test.ts` "clears a stale error when a terminal done/cancelled lands" |
| 8 | 46 | `agent/controls.tsx` | low | `FRIENDLY_TITLES` lacked `agent_rate_limited` / `agent_budget_exceeded` / `cancelled`, so those errors fell back to a generic "Error" title. Added. | covered by existing controls/AgentPanel render tests |

## Skipped findings (recorded)

- **[43 med / 47 med] End-of-file newline not modelled** — `compute_diff` (`splitlines`) drops trailing-newline-only changes, and `hunks.ts` empty-base apply can't recover a trailing newline. **Skip:** the system consistently does *not* model EOF-newline anywhere; fixing requires threading a `no_newline_at_eof` flag through the hunk schema **and** the spec-47 CRDT apply — disproportionate to the value (cosmetic, rare). No crash: `materialize_diffs` skips a no-op diff.
- **[42 low] `search_project`/`locate_section` read every doc's full content** — unbounded *scan input* (result payloads are already capped). **Skip:** project-scoped and fine for realistic projects; bounding it adds risk for little value.
- **[42 low] duplicate path+content match at line 0** in search; **[41 low] `_chunk("")`→`[""]`** (unreachable behind the `response.content` guard); **[43 low] missing `\ No newline` marker** in `diff_text` (apply uses structured hunks); **[43 low] large-file guard checks `current` only** (`new_text` already bounded at the tool). **Skip:** cosmetic / dormant / already covered.
- **[47 low] `locate()` scans `hint-d` before `hint+d`** (could relocate a hunk in highly-repetitive context) — **Skip:** unlikely with 3 context lines; changing the search order risks regressions for negligible gain. Stale hunks are still blocked by content mismatch.
- **[47 low] header shows `counts.accepted` vs confirm dialog `plan.applicable`** — **Skip:** display-only; `rebaseHunks` re-filters blocked hunks at apply, so correctness is unaffected.
- **[46 low] `seenSeqs` is an array scanned with `.includes`** — **Skip:** correct + idempotent; sessions are not long enough for the O(n) scan to matter.
- **[46 low] autoscroll `pinned` not recomputed on height-only change** — **Skip:** minor, unreported.
- **[48 low] final-section `end_char` over-inclusive of a trailing newline; unterminated verbatim degrades; first-`\documentclass`-wins; cache returns a shared mutable `ProjectMap`** — **Skip:** char ranges are advisory (consumers slice by line); the no-throw contract intends best-effort degradation (the #4 fix shrinks the verbatim trigger surface); callers treat the map as read-only.
- **[49 low] injection flag writes an audit row but no in-context "steering note"** — **Skip:** the untrusted framing + system-prompt precedence are the real mitigations; an extra steering note risks the model over-refusing legitimate edits.

## Safety / invariant outcomes (verified, not weakened)

- **No auto-apply** — confirmed by the eval suite (`test_eval_never_auto_applies`) and the diff-review tests: the backend only persists `ProposedDiff` rows; apply happens solely from the confirmed spec-47 user action as a minimal, agent-origin-tagged CRDT edit.
- **Prompt-injection resistance** — tool/document content is never placed in the system/developer role; `_frame_for_llm` wraps every tool message in `<untrusted_tool_result>` on each LLM send; the #4 parser fix removes a verbatim-opacity hole. Capability allow-list rejects+audits unknown tools.
- **Cost control** — the only LLM-calling path (`plan`) is preceded by the per-run budget checkpoint; pre-flight order is rate → day-budget → run; cancel aborts at both `plan` and `act` boundaries (no LLM call after Stop); the #1 fix removes a concurrency-slot leak; no retry multiplies cost.
- **Diff & apply correctness** — generated diffs are valid unified diffs; review applies only accepted+applicable hunks; stale hunks are blocked; collaborators converge (two-doc test); rejected hunks/files are never written.
- **Audit** — rows at every lifecycle point with redacted `detail` (no bodies/secrets); audit-write failure never crashes a run.
