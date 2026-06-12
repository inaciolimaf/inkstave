# Spec 35 — Refactor: collaboration (requirements)

## 1. Summary

A refactoring pass over everything built in Phase 4's collaboration frontend and
sharing/authz layer (specs 31–34), plus the seams where they meet the spec 28/29
server CRDT/WebSocket core. No new features. The goal is to find and fix real
defects — especially **permission holes** and **awareness/presence leaks** — to
remove smells and dead code, to close missing-test gaps, and to record a
changelog of what was changed and what was deliberately left alone, all while
keeping the suite green and under 2 minutes.

## 2. Context & dependencies

- **Depends on:** specs **31** (Yjs binding & live sync), **32** (presence/
  awareness UI), **33** (collaborators & sharing), **34** (centralized access
  control). Each must be implemented with passing tests before this pass.
- **Unlocks:** a trustworthy collaboration base for Phase 5 (history capture in
  spec 36 observes the same CRDT updates) and beyond.
- **Affected areas:** frontend collab module + editor integration; sharing
  backend (models/service/router/job) + Share UI; authorization module + the
  retrofitted guards; the spec 29 WS handler and spec 28 CRDT where 31/34 touch
  them. Docs (changelog ADR).

## 3. Goals

- Systematically **scan** the Phase-4 surface for: correctness bugs, race
  conditions, permission/authorization holes, awareness/presence leaks (ghost
  cursors, stale avatars, identity bleed across documents), resource leaks
  (un-torn-down providers/listeners/sockets), inconsistent error semantics,
  missing or weak tests, dead code, and duplication.
- **Evaluate** each finding for risk vs. value; apply only worthwhile fixes.
- **Apply** the worthwhile fixes with accompanying tests that would have caught
  the bug.
- **Keep green:** the entire suite passes and stays < 2 minutes.
- **Document:** a changelog listing every change and every consciously-skipped
  finding with a one-line rationale.

## 4. Non-goals (explicitly out of scope)

- New features, new endpoints, new UI surfaces, new env vars (unless removing one).
- Re-architecting the CRDT/WS protocol (spec 28/29 semantics are fixed); only
  fix defects in how specs 31/34 *use* it.
- Performance work beyond fixing clear inefficiencies that risk the budget or
  correctness (broad perf is spec 53).
- Anything from Phase 5+.

## 5. Detailed requirements

### 5.1 Scan checklist (areas to inspect)

The pass MUST at least inspect these known hot spots and assert they are correct
(fix if not):

**Spec 31 — binding & sync**
- Provider teardown: on document close / unmount / `documentId` change, the
  WebSocket closes, all listeners are removed, and no reconnect timer survives
  (no leaked sockets across navigation; verify under React StrictMode).
- Echo/loop prevention: local updates are not re-applied; remote updates apply
  exactly once; no duplicated text under rapid concurrent edits.
- Sync gating: editor stays read-only until first sync; no edits land on an
  un-synced base; offline→reconnect convergence has a regression test.
- Reconnect backoff is bounded and jittered; no tight reconnect loop on
  persistent auth failure (a 401/4401 should stop retrying, not spin).
- Reconciliation/`flush()` before compile actually guarantees the server sees
  current text; no stale-content compile.

**Spec 32 — presence/awareness**
- Awareness cleanup on disconnect/leave: no ghost cursors or stale avatars after
  a peer leaves or times out; local state is cleared on teardown.
- No identity/cursor bleed across documents when switching docs (awareness from
  doc A must not appear in doc B). Verify the awareness instance is per-document
  and reset on switch.
- Throttling actually bounds update volume; idle transitions set/clear correctly.
- Color determinism holds; the online list dedups by id and handles solo/overflow.

**Spec 33 — sharing**
- Single-owner invariant holds under concurrent transfer/leave attempts (no
  zero-owner or two-owner states); transactions are correctly scoped.
- Invite token secrecy: tokens are high-entropy, not leaked to non-owners, and
  (if hashed) compared safely; expired/used/revoked invites cannot be replayed.
- Email-match policy on accept is enforced; cross-project isolation holds.
- "Refresh existing pending invite" cannot create duplicates; re-invite of an
  existing member is rejected.
- The stubbed email job is enqueued exactly once per invite and is side-effect-free.

**Spec 34 — access control**
- **Permission holes (highest priority):** confirm *every* project-scoped REST
  route actually carries the central guard — grep for handlers that read
  `project_id` but lack `require_capability`/`authz.authorize`. Any unguarded
  route is a hole to fix.
- Viewer write-rejection on the WS is enforced **server-side**, not only via the
  client read-only flag; a crafted raw `update` from a viewer is dropped (not
  applied/persisted/broadcast).
- Non-member WS join is rejected; the 404-vs-403 leak policy is applied
  consistently; no endpoint leaks project existence to non-members.
- Mid-session revocation/downgrade behaves as documented (at least takes effect
  on next message/reconnect).
- The capability matrix in code matches the spec-34 table exactly (no drift).

**Cross-cutting**
- Consistent typed errors and status codes across the collab/sharing/authz
  surface; no leaking stack traces or internal messages.
- No dead code, commented-out blocks, or unused exports left by Phase 4.
- Duplicated logic (e.g. membership lookups) consolidated into the authz service.

### 5.2 Process requirements

- Produce a written **evaluation** for each non-trivial finding: severity,
  likelihood, blast radius, and a keep/fix/defer decision. Defer items that are
  real but better handled by a named later spec (e.g. broad perf → 53,
  observability → 51), citing it.
- For every applied fix, add or update a test that fails before and passes after
  (where feasible for the bug class). Security/permission fixes MUST get a test.
- Keep changes minimal and behaviour-preserving for legitimate flows; do not
  refactor for taste in ways that risk regressions.

### 5.3 Changelog

- A `docs/refactors/35-collaboration.md` (or the established refactor-log
  location) listing: each change (what, why, files), each finding deliberately
  **skipped/deferred** (with rationale + target spec), and the before/after of any
  acceptance-criterion correction. Reference this from `docs/`.

### 5.4–5.5 (data model / config)

- No intentional data-model changes. If a fix needs an index or a constraint to
  close a real bug (e.g. the partial unique index enforcing single-owner or
  single-pending-invite from spec 33), ship a forward-only Alembic migration and
  note it in the changelog.
- No new env vars; remove any now-unused ones found during the scan (documenting
  the removal in `.env.example` and the changelog).

## 6. Overleaf reference (study only — never copy)

None. This is an internal refactor driven by Inkstave's own code and the
acceptance criteria of specs 31–34. The no-copy rule still applies.

## 7. Acceptance criteria

1. A documented scan of the spec 31–34 surface exists, covering at least the §5.1
   checklist, each item marked verified-correct or fixed.
2. Every applied fix is accompanied by a test that exercises the fixed behaviour;
   all security/permission fixes have a regression test.
3. **No permission holes remain:** an automated test (or documented audit) shows
   every project-scoped REST route is guarded, and the WS viewer-write-rejection
   and non-member-join-rejection hold server-side.
4. **No awareness leaks remain:** tests confirm no ghost cursors/stale avatars
   after disconnect and no presence/identity bleed across documents.
5. The full test suite passes and runs in **< 2 minutes**; coverage of the
   collaboration surface is not reduced (ideally increased).
6. A changelog records every applied change and every deliberately-skipped
   finding with rationale (and target spec for deferrals).
7. No new features were added; no behavioural regression for legitimate
   owner/editor/viewer flows (prior specs' acceptance criteria still pass).

## 8. Test plan

> Keep the full suite under 2 minutes. Reuse the in-process two-Yjs-client
> harness (spec 31) and the table-driven authz matrix tests (spec 34); avoid
> adding new browser e2e unless a fix specifically needs one.

- **Unit / integration additions (pytest):**
  - Regression tests for each applied backend fix (sharing invariants, invite
    replay/expiry, authz guard coverage, WS viewer-write-rejection at the server).
  - An automated guard-coverage check: enumerate project-scoped routes and assert
    each requires a capability (fails on any unguarded route).
- **Unit / integration additions (Vitest):**
  - Regression tests for provider teardown/leaks, awareness cleanup on
    disconnect, no cross-document presence bleed, sync-gating, reconnect-stop on
    auth failure.
- **E2E (Playwright):** only if a fix can't be proven otherwise; keep to existing
  minimal two-context tests from 31/32. No new heavy e2e.
- **Performance/budget note:** measure suite runtime before and after; if any
  added test threatens the budget, move slow assertions to in-process harnesses
  or mark/optimize. Record the runtime in the changelog.

## 9. Definition of Done

- [ ] §5.1 scan completed and documented; each item verified or fixed.
- [ ] All worthwhile fixes applied with accompanying tests; permission/awareness
      fixes have regression tests (AC 2–4).
- [ ] No permission holes and no awareness leaks remain (AC 3–4).
- [ ] Full suite green and < 2 minutes; collaboration coverage not reduced (AC 5).
- [ ] Lint/format/type-check clean.
- [ ] Changelog written listing applied changes and skipped/deferred findings
      with rationale (AC 6); any forward-only migration noted.
- [ ] No new features; no regression to specs 31–34 acceptance criteria (AC 7).
- [ ] No Overleaf code copied.
