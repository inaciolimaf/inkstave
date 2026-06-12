# Spec 30 — Refactor pass over the real-time core (requirements)

## 1. Summary

A refactoring spec (no new features) covering everything built in specs 28
(server-side CRDT model, persistence, content bridge) and 29 (JWT WebSocket,
rooms, Redis fan-out, lifecycle). Scan the real-time core for **concurrency
races, memory growth (unbounded rooms/connections/in-memory docs), reconnect
correctness, persistence integrity, leaks, and missing tests**; evaluate each
finding for risk vs. value; apply the worthwhile fixes while keeping all tests
green; and record a changelog of what changed and what was deliberately skipped.

## 2. Context & dependencies

- **Depends on:** **spec 28** and **spec 29** (the code under review). Their tests
  must be green before starting.
- **Unlocks:** a solid base for spec 31 (frontend binding) and spec 32 (presence
  UI), which will hammer this layer with real browser traffic.
- **Affected areas:** backend `backend/app/collab/` (CRDT model, store, manager,
  content bridge, awareness) and `backend/app/collab/ws/` (endpoint, rooms, redis
  bridge); test suites for both; `docs/` changelog. No frontend.

## 3. Goals

- Find and fix real defects in the real-time core, prioritised by likelihood and
  blast radius.
- Strengthen the test suite so each fixed bug has a regression test and the most
  important invariants are covered.
- Keep behaviour identical except where a change is a clear bug fix; keep the full
  suite green and under 2 minutes.
- Produce a written changelog (applied vs. skipped, with rationale).

## 4. Non-goals (explicitly out of scope)

- New features of any kind (frontend binding, presence UI, sharing, roles, finer
  authz) — specs 31–34.
- Swapping libraries or the CRDT algorithm.
- Broad rewrites for taste; only changes justified by a concrete finding.
- Performance work beyond fixing unbounded-growth/leak issues (general perf tuning
  is spec 53).

## 5. Detailed requirements

This spec is executed as a **scan → evaluate → apply → verify → record** loop.

### 5.1 Scan checklist (areas to audit)

For each area, look for the listed failure modes and write a finding (severity,
location, evidence, proposed fix or "skip" with reason).

**A. Concurrency & races (spec 28 manager, spec 29 loops)**
- Double-load of a `YDocument` under concurrent `acquire` (is the load lock
  correct and per-document, not global?).
- Refcount race: interleaved `acquire`/`release` driving refcount negative or
  evicting a doc that still has connections.
- Update applied to the CRDT but not (or doubly) appended to `crdt_update`, or
  appended but not relayed, on exceptions mid-handler.
- Awareness registry mutation races across connections of the same document.
- Writer-task vs. close race: enqueue after socket close; task cancellation
  ordering on disconnect; partial frame writes.
- Redis forwarder task and room teardown racing (message delivered to a torn-down
  room; double-unsubscribe).

**B. Memory / unbounded growth**
- Rooms map entries never removed when the last connection leaves (local) or when
  the last instance leaves (Redis subscription lingering).
- In-memory `YDocument`s never evicted (idle-eviction actually fires; timers not
  leaked/duplicated).
- `crdt_update` log growing without compaction (compaction trigger actually runs;
  thresholds honoured; deleted rows match the snapshotted high-water mark).
- Per-connection `send_queue` unbounded, or bounded but never drained on a dead
  socket; awareness state for departed clients never pruned.
- Background tasks (writer, ping, redis forwarder) accumulating across
  connect/disconnect cycles.

**C. Reconnect correctness**
- A client that drops and reconnects converges (re-runs the sync handshake from
  its current state vector; no lost or duplicated updates).
- Updates published to Redis while a room is momentarily empty on one instance but
  present on another are not lost for the present instance.
- Awareness "offline" is reliably emitted on abrupt disconnect (not only graceful).
- Origin-exclusion across Redis loopback still correct after reconnect (new
  connection id).

**D. Persistence integrity**
- `CrdtStore.load` rebuilds exactly: snapshot then ordered log; no off-by-one in
  the compaction high-water mark (an update at the boundary is neither lost nor
  double-applied).
- Compaction transaction is atomic (snapshot write + log delete together; a crash
  between them cannot corrupt state).
- The content bridge cannot create a feedback loop (spec-13 write re-emitting a
  CRDT update) and is idempotent; debounce/flush-on-release actually persists the
  final text (no lost last edit on the close path).
- `text_synced_seq` is maintained so a recovered process does not silently serve
  stale text.

**E. Auth / security (transport)**
- JWT verified **before** `accept()`/room join in every path; expired token mid-
  session handled per policy (decide & document: keep until disconnect vs. reject
  on next message — pick one and make it consistent).
- The collaborator stub is actually enforced for both project and document
  ownership (document belongs to project).
- Close codes used consistently; no information leak in close reasons.
- Frame-size and rate limits enforced on every inbound path.

**F. Tests & observability**
- Missing tests for the invariants above (convergence under reorder, cross-
  instance relay, disconnect cleanup, compaction boundary, reconnect).
- Flaky timing tests (replace sleeps with deterministic waits/short injected
  timeouts).
- Logging adequate to debug a stuck room (connection counts, room lifecycle,
  compaction events) without being noisy.

### 5.2 Evaluate

For every finding, classify severity (**critical** data-loss/corruption/race that
diverges state · **high** leak/unbounded growth/security · **medium** correctness
edge case · **low** cleanliness) and decide **apply** or **skip**. Apply criteria:
fixes a real bug, prevents unbounded growth, closes a race, or adds a missing
high-value test, with risk proportionate to value. Skip: speculative, low-value,
or risky changes without a demonstrated problem — record why.

### 5.3 Apply

- Make minimal, behaviour-preserving changes (except clear bug fixes). Each
  applied fix that addresses a bug ships with a **regression test** that fails
  before and passes after.
- Keep the public contracts from specs 28/29 stable (spec 31 depends on them); if
  a contract must change, note it explicitly in the changelog and update callers.
- Prefer deterministic concurrency tests (e.g. `anyio`/`asyncio` task
  orchestration, barriers) over sleeps.

### 5.4 Configuration

No new runtime config expected. If a fix requires a tunable (e.g. a corrected
eviction/compaction bound), reuse the existing `COLLAB_*` settings; only add a new
env var if unavoidable and then document it in `.env.example`.

## 6. Overleaf reference (study only — never copy)

None. This is an internal refactor of Inkstave-original code. Do not consult or
copy Overleaf for this spec.

## 7. Acceptance criteria

1. **Findings recorded.** A `docs/` changelog lists every finding from §5.1 with
   severity and an apply/skip decision and rationale.
2. **Worthwhile fixes applied.** All findings rated critical/high that pass the
   §5.2 apply criteria are fixed; skipped ones have a written reason.
3. **Regression tests added.** Every applied bug fix has a test that fails on the
   pre-fix code and passes after.
4. **Concurrency invariants tested.** There exist deterministic tests for: single
   load under concurrent `acquire`; refcount never negative; no eviction while
   connections remain; convergence under reordered/concurrent updates.
5. **Memory bounded.** A test demonstrates that repeated connect/disconnect and
   open/close cycles leave the rooms map empty, evict idle docs, and do not leak
   background tasks (task count returns to baseline).
6. **Reconnect correctness tested.** A drop-and-reconnect test shows the client
   re-syncs and converges with no lost/duplicated updates.
7. **Persistence integrity tested.** A compaction-boundary test confirms
   `load` reproduces exact state across snapshot+truncate, and a flush-on-release
   test confirms the final edit is persisted.
8. **Green & on budget.** The entire test suite passes and runs in under 2
   minutes; no new flakiness (timing tests deterministic).
9. **Lint/type clean.** ruff + mypy/pyright clean across the changed code.
10. **No scope creep.** `git diff` contains only refactors/fixes/tests for the
    spec-28/29 surface (plus the changelog) — no new feature code.

## 8. Test plan

> Same fast tiers as 28/29: pure CRDT unit tests + async WS client integration
> tests with fake/local Redis and the test DB. No real network, LLM, or LaTeX.

- **Unit (pytest):** new/updated tests for any fixed race or boundary in the
  manager, store, awareness, room manager, and redis bridge. Replace sleep-based
  waits with deterministic synchronisation.
- **Integration (pytest + ASGI WS client + fake/test Redis + test DB):**
  - Connect/disconnect and open/close leak tests (criterion 5): assert rooms map
    empties, idle eviction fires (short injected interval), background-task count
    returns to baseline.
  - Reconnect convergence (criterion 6).
  - Cross-instance relay still correct after the refactor.
  - Compaction-boundary persistence (criterion 7) on the test DB.
- **Performance/budget note:** keep added tests in-process and fast; use injected
  short timers for eviction/compaction; assert task/queue counts rather than
  sleeping. Confirm total suite time after changes stays < 2 min (record the
  number in the changelog).

## 9. Definition of Done

- [ ] Scan completed across all §5.1 areas; findings recorded in a `docs/`
      changelog with severity + apply/skip rationale.
- [ ] All worthwhile (critical/high, and justified medium) fixes applied.
- [ ] Every applied bug fix has a regression test (fails before / passes after).
- [ ] All acceptance criteria in §7 pass.
- [ ] Full suite green and under 2 minutes (time recorded in the changelog).
- [ ] Lint/format/type-check clean.
- [ ] Public contracts from specs 28/29 preserved (or changes documented and
      callers updated).
- [ ] No new feature code; no Overleaf code copied.
