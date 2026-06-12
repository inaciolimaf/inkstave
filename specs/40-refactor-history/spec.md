# Spec 40 — Refactor: History & Notifications (requirements)

## 1. Summary

A refactoring pass over Phase 5 (specs 36–39). It systematically scans the history
capture/storage, history API (list/diff/restore/labels), history UI, and the
notifications + email subsystem for bugs, storage bloat, restore-correctness flaws,
email-job reliability issues, and missing tests. Each finding is evaluated for
risk vs. value; only worthwhile fixes are applied. The suite stays green and under
2 minutes, and a changelog records what was changed and what was deliberately
skipped. **No new features.**

## 2. Context & dependencies

- **Depends on:** specs **36** (history capture), **37** (history API), **38**
  (history UI), **39** (notifications & email) — all implemented with passing tests.
- **Unlocks:** a stable Phase 5 base for the AI agent phase (specs 41+).
- **Affected areas:** backend (history service/jobs, API, notifications, email),
  frontend (history UI, notifications bell), tests, docs (changelog + ADRs).

## 3. Goals

- Identify and fix correctness bugs across specs 36–39, prioritising:
  - **Restore correctness** — a restore must reproduce the target text exactly, create a
    new version, never destroy history, and converge all live clients.
  - **History reconstruction** — `reconstruct_state` and diff must be exact across chunk
    boundaries and after compaction (gaps tolerated, no corruption).
  - **Email-job reliability** — enqueue-not-block invariant, retry/idempotency behaviour,
    and the no-real-SMTP-in-tests guarantee.
- Reduce **storage bloat**: redundant/oversized history payloads, missed blob offloads,
  un-sealed runaway chunks, un-swept expired notifications, duplicate invite notifications.
- Close **test gaps**: add tests for any fixed bug and any high-value uncovered path.
- Improve internal quality (naming, dead code, error handling, transaction boundaries,
  index usage) where low-risk and worthwhile.
- Keep all public contracts and behaviour stable (except outright bug fixes, recorded).

## 4. Non-goals (explicitly out of scope)

- New features, endpoints, UI screens, or config (beyond fixing/removing what exists).
- Re-architecting the capture/storage model unless a concrete bug demands it (recorded).
- Performance work unrelated to the suite budget or storage bloat.
- Anything in later phases (AI agent, hardening, packaging).

## 5. Detailed requirements

### 5.1 Review checklist (must be performed and its results recorded)

Run a structured review across these areas and record findings (file/line, severity,
decision: fix / skip + reason):

**Spec 36 — capture & storage**
- Debounce/flush: lost updates on shutdown or room-empty; timer leaks; per-doc lock
  correctness; threshold-vs-idle interaction; multi-worker buffering assumption holds.
- Version monotonicity: no duplicate/missing `version`; unique constraint actually
  enforced; de-dupe by hash works and does not drop legitimate identical edits wrongly.
- Chunking: exactly-one-open-chunk invariant (partial unique index) holds under
  concurrency; chunk sealing at threshold; base snapshot correctness.
- Offload: inline-vs-blob invariant (exactly one non-NULL); `*_size` accuracy; orphaned
  blobs on failed writes; blob key prefix usage.
- Compaction job: idempotency; never reduces restorable set (beyond intended merge of
  adjacent intermediates); safe re-run; transaction atomicity; reconstructed state
  unchanged after merge.

**Spec 37 — API & restore**
- Diff: hunk/segment correctness across edge cases (empty doc, all-added, all-removed,
  trailing newline); `to=current` path; binary + too-large guards; size guard before work.
- Restore: atomicity (no partial state on room-failure → 409); applies as a single CRDT
  transaction; produces a new version; history intact; label attaches to the *new*
  version; project restore per-doc independence.
- Pagination over compaction gaps terminates; author joins handle NULL authors.
- Authz matrix enforced on every endpoint; non-member → 404, under-privileged → 403; no
  cross-project leakage via label/version IDs.

**Spec 38 — history UI**
- Loading/empty/error states present; pagination correctness; selection model (single vs
  range) bugs; diff fallback rendering; restore confirmation copy + flow; no direct editor
  mutation; a11y (markers not colour-only, focus trapping).

**Spec 39 — notifications & email**
- Email always enqueued (never inline); job retry/idempotency; SMTP failure re-raises;
  sender factory selection; no real SMTP in tests.
- Notifications: ownership enforcement (cross-user 404); de-dupe of invite notifications;
  expiry exclusion + sweep idempotency; index usage for active-listing.
- Frontend bell: optimistic update rollback; poll interval; accept-invite wiring.

### 5.2 Apply worthwhile fixes

- For each finding marked **fix**: implement the minimal correct change, add/adjust tests
  to lock in the behaviour, and keep all existing tests green.
- For each marked **skip**: record a one-line justification (low value, high risk, or out
  of scope) in the changelog.
- Storage-bloat fixes may include: enforcing offload thresholds that were missed, sealing
  runaway open chunks, removing duplicate notification rows, ensuring the sweep runs in
  the worker config, and deleting orphaned blobs (only when provably unreferenced).

### 5.3 Backend / API

- No new endpoints. Bug fixes to existing endpoints must preserve request/response
  contracts; any contract change that is itself the bug fix is documented in the changelog
  with before/after.

### 5.4 Frontend / UI

- No new screens. Fixes to existing components only.

### 5.5 Configuration

- No new env vars. If a default was wrong/unsafe (e.g. a too-large inline threshold), it
  may be corrected with a changelog note; otherwise leave config untouched.

### 5.6 Changelog (required deliverable)

- Produce `docs/refactors/40-history-notifications.md` listing, per finding:
  area/spec, file, severity, decision (applied/skipped), rationale, and (for applied)
  the test that now covers it. Summarise storage-bloat and restore-correctness outcomes.

## 6. Overleaf reference (study only — never copy)

None. This spec operates only on Inkstave's own Phase-5 code. The originality rule still
applies: do not introduce any Overleaf-derived code.

## 7. Acceptance criteria

1. The §5.1 review checklist has been executed and its findings recorded in the §5.6
   changelog with a fix/skip decision and rationale for each.
2. Every finding marked **fix** is implemented, covered by a test, and the full suite is
   green.
3. **Restore correctness** is verified by tests: after a restore, the live document text
   equals the target version's text, a new version exists, all prior `history_*` rows
   remain, and (mocked) clients receive the update.
4. **History reconstruction** is exact across chunk boundaries and after a compaction run
   (verified by a test that captures, seals chunks, compacts, then reconstructs/diffs).
5. **Storage bloat** issues found are addressed: e.g. oversized inline payloads are
   offloaded, runaway open chunks are sealed, expired notifications are swept, duplicate
   invite notifications are prevented — each demonstrated by a test or a measured before/
   after noted in the changelog.
6. **Email reliability**: tests confirm email is only enqueued (never sent inline in a
   request), the job re-raises on transient failure for retry, and no test opens a real
   SMTP connection.
7. No public API/route contract changed except where a change is itself a documented bug
   fix in the changelog.
8. No restorable history version is lost and no access-control rule is weakened relative
   to specs 36–39 (asserted by retained/added authz and history-integrity tests).
9. The full test suite passes and runs in **under 2 minutes**; lint/format/type-check are
   clean.
10. `docs/refactors/40-history-notifications.md` exists and documents applied vs. skipped
    findings with rationale.

## 8. Test plan

> Keep the suite under 2 minutes. Reuse the fast tiers; no real SMTP, no real WebSocket
> server, no real LaTeX. The compaction and sweep schedulers stay mocked; job bodies are
> invoked directly.

- **Unit (pytest / Vitest):** add targeted tests for each fixed bug (regression tests).
  Cover the specific edge cases surfaced in §5.1 (diff edge cases, debounce shutdown
  flush, de-dupe, sender selection, etc.).
- **Integration (pytest + httpx + test Postgres + fake Redis + ARQ harness):**
  - Restore correctness + history integrity end-to-end (criterion 3).
  - Capture → seal → compact → reconstruct/diff exactness (criterion 4).
  - Storage-bloat fixes (offload, chunk sealing, sweep, invite de-dupe) (criterion 5).
  - Email enqueue-not-inline + retry-on-failure with the capturing fake (criterion 6).
  - Authz/history-integrity regression suite (criterion 8).
- **E2E (Playwright):** re-run the existing Phase-5 flows (history view + restore;
  notifications bell) against stubbed/seeded backends to confirm no regression. Add a
  flow only if a fixed bug needs end-to-end coverage.
- **Performance/budget note:** Confirm and record the suite runtime; if any fix risks
  slowing tests, keep slow work in mocked jobs. Re-measure before completing.

## 9. Definition of Done

- [ ] §5.1 review performed; all findings recorded with decisions.
- [ ] All **fix**-marked findings applied and covered by tests; all acceptance criteria
      in §7 pass.
- [ ] Full suite passes and runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] No restorable history lost; no authz weakened; public contracts stable (except
      documented bug fixes).
- [ ] `docs/refactors/40-history-notifications.md` changelog written (applied + skipped
      with rationale).
- [ ] No Overleaf code copied.
