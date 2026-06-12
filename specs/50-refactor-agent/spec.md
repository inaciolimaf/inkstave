# Spec 50 — Refactor: Full AI Agent (requirements)

## 1. Summary

A refactoring pass over the **entire** AI agent feature (specs 41–49). It
systematically scans the agent core (LangGraph graph + DI-injected LLM client),
tools, per-file diff generation, the streaming chat API/ARQ orchestration, the
browser chat panel, the diff review/apply flow, the LaTeX context/section parser,
and the safety/eval layer for bugs, prompt-injection holes, cost traps, UX
issues, and missing tests. Each finding is evaluated for risk vs. value; only
worthwhile fixes are applied. The suite stays green and under 2 minutes, the eval
suite stays deterministic, and a changelog records what was changed and what was
deliberately skipped. **No new features.**

## 2. Context & dependencies

- **Depends on:** specs **41** (agent foundation), **42** (tools), **43** (diff
  generation), **44** (streaming API/ARQ), **45** (agent-core refactor), **46**
  (chat UI), **47** (diff review/apply), **48** (context/section parsing), **49**
  (safety & evals) — all implemented with passing tests.
- **Unlocks:** a stable, production-ready agent for Phase 7 (hardening,
  packaging, e2e, docs).
- **Affected areas:** backend (agent package: graph, tools, diff, streaming,
  context, safety, audit), frontend (chat panel, diff review), tests (incl. the
  eval suite), docs (changelog + ADRs).

## 3. Goals

- Identify and fix correctness bugs across specs 41–49, prioritising:
  - **Safety invariants** — the agent never auto-applies a diff; apply is
    user-confirmed only (spec 47); untrusted document/tool content is always
    framed and never elevated to system/developer role (spec 49); rate
    limits/budgets are enforced before and during runs; audit rows are written.
  - **Prompt-injection resistance** — re-examine prompt assembly and tool-result
    handling for any path where untrusted content could change agent behaviour,
    leak the system prompt, or trigger a disallowed action.
  - **Cost/runaway control** — no path that calls the LLM without budget
    accounting; no unbounded loops/recursion in the graph; bounded tool-call
    counts; mid-run budget checkpoints actually stop runs; streaming
    backpressure/cancellation truly aborts server work (no orphaned ARQ jobs or
    leaked LLM calls after Stop).
  - **Diff correctness** — generated unified diffs are valid and apply cleanly;
    base-version/rebase handling in review (47) never silently clobbers
    concurrent edits; CRDT apply produces minimal edits, not full replaces.
- Smooth **UX issues** in the chat panel and diff review: streaming/scroll
  glitches, stuck "working" indicators after error/cancel, hunk toggle/preview
  desync, accessibility gaps, confusing error copy for limit/budget/transport
  errors.
- Close **test gaps**: add tests for any fixed bug and any high-value uncovered
  path; keep the eval suite (49) deterministic and meaningful.
- Improve internal quality (naming, dead code, error handling, DI seams,
  reducer purity, transaction boundaries) where low-risk and worthwhile.
- Keep all public contracts and behaviour stable (except outright bug fixes,
  recorded).

## 4. Non-goals (explicitly out of scope)

- New agent capabilities, tools, models, UI screens, or config (beyond
  fixing/removing what exists).
- Re-architecting the graph, diff format, or streaming protocol unless a concrete
  bug demands it (recorded).
- Embeddings/vector retrieval or any new external integration.
- Work belonging to Phase 7 (general observability/security hardening, Docker,
  CI/CD, docs) — except where a finding is squarely an agent bug.

## 5. Detailed requirements

### 5.1 Review checklist (must be performed and its results recorded)

Run a structured review across these areas and record findings (file/line,
severity, decision: fix / skip + reason):

**Spec 41 — foundation (graph + DI LLM client)**
- LLM client is always obtained via DI (no hard-coded provider/base URL/key in
  business logic); FakeLLM truly substitutes it in every test path.
- Graph state typing/immutability; no shared mutable state across runs;
  cancellation token honoured at graph boundaries; no unbounded recursion.

**Spec 42 — tools**
- Each tool validates inputs; `read_file`/`search_project` cannot escape the
  project (path traversal / cross-project reads); results bounded in size.
- `locate_section` delegates to spec 48; `propose_edit` never writes documents.
- Tool errors are surfaced (not swallowed) and audited.

**Spec 43 — diff generation**
- Diffs are syntactically valid unified diffs; correct base captured; new-file/
  deletion/empty-file/no-trailing-newline edge cases; never auto-applied; large
  files guarded.

**Spec 44 — streaming API / ARQ**
- Auth/authz on every endpoint (only project members can run/list/stream);
  session/run ownership enforced; cancel actually aborts server work (no orphaned
  job, no continued LLM billing); stream reconnect/replay (if any) is idempotent;
  error events use the documented codes; no secret leakage in events.

**Spec 46 — chat UI**
- Stream reducer is pure/idempotent (no duplicate items on replay); working
  indicator clears on done/error/cancel; autoscroll/jump-to-latest correctness;
  composer disabled/enabled transitions; markdown sanitization (no script exec,
  no auto-fetch); limit/budget/transport error states render with correct copy;
  a11y (live region, keyboard, focus).

**Spec 47 — diff review / apply**
- Apply writes only accepted, applicable hunks as a **CRDT** update tagged with
  an agent origin; minimal edit (not full replace); rejected hunks/files never
  written; base-changed detection blocks stale hunks; confirm-before-apply gates
  every apply; no path applies without explicit user confirmation; concurrent
  collaborator convergence; a11y (add/remove conveyed non-visually, focus trap).

**Spec 48 — context / section parsing**
- Parser never throws on malformed LaTeX; ranges correct across chunk/section
  boundaries; verbatim/comment opacity; include-cycle guard; `select_context`
  never exceeds the token budget; deterministic truncation; cache correctness
  (same results with/without cache).

**Spec 49 — safety & evals**
- Rate limits and per-run/per-day budgets enforced with overridable env values
  (no hard-coded caps); injection framing + capability allow-list intact; audit
  rows written without secrets/full document bodies; audit-write failure does not
  crash a run; the eval suite is deterministic and asserts the invariants
  (section location, valid diffs, budget/limit enforcement, injection resistance,
  never auto-applies).

### 5.2 Apply worthwhile fixes

- For each finding marked **fix**: implement the minimal correct change, add or
  adjust tests to lock in the behaviour, and keep all existing tests green.
- For each marked **skip**: record a one-line justification (low value, high
  risk, or out of scope) in the changelog.
- Cost-trap fixes may include: adding a budget checkpoint to a missed LLM-calling
  path, bounding tool-call/loop counts, ensuring Stop/cancel truly aborts the ARQ
  job and the in-flight LLM stream, and removing any retry that could silently
  multiply cost.
- Injection fixes may include: tightening untrusted-content framing, removing any
  path that concatenates document/tool text into system/developer roles, and
  hardening the tool capability allow-list.

### 5.3 Backend / API

- No new endpoints. Bug fixes to existing endpoints must preserve request/
  response and streaming-event contracts; any contract change that is itself the
  bug fix is documented in the changelog with before/after.

### 5.4 Frontend / UI

- No new screens or components. Fixes to existing chat-panel and diff-review
  components only. Preserve the spec-46 entry-point contract
  (`onReviewProposal`) and the spec-47 apply behaviour.

### 5.5 Configuration

- No new env vars. If a default limit/budget was unsafe (e.g. an effectively
  unbounded cap), it may be corrected with a changelog note; otherwise leave
  config untouched. All caps remain env-overridable.

### 5.6 Changelog (required deliverable)

- Produce `docs/refactors/50-agent.md` listing, per finding: area/spec, file,
  severity, decision (applied/skipped), rationale, and (for applied) the test
  that now covers it. Summarise the safety, prompt-injection, cost-trap, and
  diff-correctness outcomes explicitly.

## 6. Overleaf reference (study only — never copy)

None. The AI agent has **no Overleaf equivalent**, and this spec operates only on
Inkstave's own agent code (specs 41–49). The originality rule still applies: do
not introduce any Overleaf-derived code.

## 7. Acceptance criteria

1. The §5.1 review checklist has been executed and its findings recorded in the
   §5.6 changelog with a fix/skip decision and rationale for each.
2. Every finding marked **fix** is implemented, covered by a test, and the full
   suite is green.
3. **No auto-apply** is verified by tests: no code path applies a diff to a
   document without explicit spec-47 user confirmation (the safety invariant from
   spec 49 still holds after refactoring).
4. **Prompt-injection resistance** is verified: untrusted document/tool content
   is framed and never elevated to system/developer role; injection fixtures do
   not change agent behaviour, leak the system prompt, or trigger a disallowed
   action (regression tests added for any hole found).
5. **Cost control** is verified: every LLM-calling path is budget-accounted; runs
   stop at mid-run budget checkpoints; Stop/cancel aborts server work with no
   orphaned ARQ job or continued LLM call (asserted with mocks/fakes).
6. **Diff & apply correctness** is verified: generated diffs are valid; review
   applies only accepted/applicable hunks as a minimal CRDT update tagged with an
   agent origin; base-changed hunks are blocked; collaborators converge; rejected
   hunks/files are never written.
7. **Context/parser correctness** is verified: parser does not throw on malformed
   input; `select_context` never exceeds the budget; cache yields identical
   results.
8. No public API/route/streaming-event contract changed except where a change is
   itself a documented bug fix in the changelog.
9. No safety invariant is weakened relative to specs 41–49 (rate limits, budgets,
   injection framing, audit, no-auto-apply) — asserted by retained/added tests;
   the eval suite remains deterministic and green.
10. The full test suite passes and runs in **under 2 minutes**; lint/format/
    type-check are clean.
11. `docs/refactors/50-agent.md` exists and documents applied vs. skipped
    findings with rationale.

## 8. Test plan

> Keep the suite under 2 minutes. Reuse the fast tiers; **no real LLM and no
> external network** anywhere. Use FakeLLM / recorded fixtures, fakeredis, a test
> DB, and in-process CRDT docs. ARQ job bodies are invoked directly; rate-window
> timing uses an injected fake clock.

- **Unit (pytest / Vitest):** add targeted regression tests for each fixed bug.
  Cover edge cases surfaced in §5.1 (graph cancellation, tool path-escape,
  reducer idempotency, sanitization, hunk-apply edge cases, parser malformed
  input, budget checkpoint math, injection framing).
- **Integration (pytest + httpx + fakeredis + test DB + ARQ harness):**
  - End-to-end agent run via the spec-44 path with FakeLLM: assert enforcement
    order (rate → budget pre-check → framed prompt → checkpoints), audit rows
    land, and cancel aborts the job with no further LLM calls (criteria 3, 5, 9).
  - Diff propose → review → apply with an in-process Yjs doc and a synced second
    doc: assert minimal CRDT apply, blocked stale hunks, collaborator convergence,
    and no auto-apply (criteria 3, 6).
  - Context/parser regression fixtures (criterion 7).
- **Eval suite (spec 49):** re-run; assert it remains deterministic, fast, and
  green, and extend it for any newly-found safety hole (criteria 4, 9).
- **E2E (Playwright):** re-run the existing Phase-6 flows (open panel → run →
  stream → review → apply; Stop on a long run; a forced limit/budget error)
  against a FakeLLM-backed backend to confirm no regression. Add a flow only if a
  fixed bug needs end-to-end coverage.
- **Performance/budget note:** Confirm and record the suite runtime; keep all
  slow work mocked; re-measure before completing.

## 9. Definition of Done

- [ ] §5.1 review performed; all findings recorded with decisions.
- [ ] All **fix**-marked findings applied and covered by tests; all acceptance
      criteria in §7 pass.
- [ ] Full suite passes and runs in < 2 minutes; the eval suite stays
      deterministic and green.
- [ ] Lint/format/type-check clean.
- [ ] No safety invariant weakened (no auto-apply; injection framing; budgets/
      limits; audit); public contracts stable (except documented bug fixes).
- [ ] `docs/refactors/50-agent.md` changelog written (applied + skipped with
      rationale).
- [ ] No Overleaf code copied (no agent equivalent exists).
