# Refactor 35 — Collaboration (specs 31–34)

A hardening pass over Phase 4: the frontend Yjs binding (31), presence (32),
sharing (33), and centralized access control (34), plus the seams where they meet
the spec 28/29 CRDT/WS core. **No new features, no behavioural regressions.**

## Baseline → After

| Suite | Before | After |
| --- | --- | --- |
| **Backend** (`pytest backend/tests`) | 554 passed, 1 skipped, ~36 s | **556 passed, 1 skipped, 39.3 s** |
| **Frontend** (`vitest run`) | 258 passed | **262 passed** |

Combined ≈ 52 s — well under the 2-minute budget. `ruff` + `mypy` (115 files) +
`eslint` + `tsc` clean.

## Method

scan (§5.1 checklist) → evaluate (severity/likelihood/blast radius) → apply only
worthwhile fixes with a regression test → keep green → record. Each applied fix
ships a test that fails on the pre-fix code; security/permission work is covered
by an automated audit.

## Applied fixes

| id | area | finding | sev | fix + test |
| --- | --- | --- | --- | --- |
| F-1 | 31 provider | **Reconnect spin on terminal auth/permission close.** `_onClose` ignored the WS close code and always scheduled a backoff reconnect — a 4401 (bad/expired token), 4403 (non-member/removed) or 4404 (deleted doc) would retry forever, never recovering, burning the socket + battery. | **high** | `InkstaveWsProvider` now reads `event.code`; on a `TERMINAL_CLOSE_CODES` (4401/4403/4404) it sets `_stopped`, goes `closed`, emits `connection-error`, and **does not reconnect**. Tests: "stops reconnecting after a terminal auth close (4401)" + a parametrized 4403/4404 case (assert exactly one socket ever created across 60 s of fake time). |
| F-2 | 34 authz | **Dead code + duplicated membership lookup.** `AuthorizationService` was never instantiated anywhere (the `require_capability` dependency uses a single project+role outer-join; `role_for` covers WS/compile/`/permissions`). It carried a second, divergent role-cache implementation. | med | Removed the class (and its `__init__`/`__all__` export). The membership lookup now lives in exactly two purpose-built helpers: `role_for` (role-only) and the dependency's one-query `_resolve` (project+role). No behaviour change. **No paired regression test** — see the §5.2 feasibility note below. |

## Added tests (closing real gaps)

| id | AC | test |
| --- | --- | --- |
| T-1 | 35 AC3 | **Guard-coverage audit** (`test_authz_guard_coverage.py`): enumerates every `{project_id}` REST route on the real app and asserts each carries the `require_capability` marker **or** is in a small, hand-audited `_HANDLER_GUARDED` allowlist (sharing routes guarded by the sharing service; `/permissions` + SSE `/events` guarded by `role_for` in-handler). A second test asserts the allowlist references only real routes. **Fails the moment any future project route is added unguarded** — the permission-hole class is now machine-checked. `require_capability` gained a `__authz_capability__` marker for this. |
| T-2 | 35 AC4 | **No cross-document presence bleed** (`useCollabDoc.test.ts`): set awareness on doc A, switch `documentId` to B, assert B's awareness is a fresh instance (different `clientID`) with none of A's states. |
| T-3 | 31 | The F-1 terminal-close regression tests above. |

## Verified-correct (no change needed)

- **31 teardown / StrictMode:** provider `destroy()` is idempotent, removes doc +
  awareness listeners, cancels the reconnect + awareness-throttle timers, and
  closes the socket; the StrictMode double-mount test confirms one live socket and
  clean teardown.
- **31 echo/loop + sync gating + offline→reconnect:** covered by the two-client
  convergence, echo-prevention, sync-gating, and offline-merge tests.
- **31 reconciliation `flush()`:** resolves once the outbound queue drains; the
  server holds the text (provider test). The compile path can await it.
- **32 awareness cleanup / ghost cursors:** `destroy()` broadcasts the awareness
  removal before detaching; the disconnect test asserts a peer's presence clears.
  Idle set/clear + throttle bounding + color determinism + dedup/overflow all
  tested.
- **33 single-owner invariant:** the partial unique index `uq_membership_one_owner`
  (`WHERE role='owner'`) enforces it at the DB; transfer flushes demote-before-
  promote so the index is never transiently violated. Token secrecy: hashed at
  rest, raw only in the create response, never in any list (asserted); expired/
  revoked/declined invites → 410 (cannot replay); email-match + cross-project
  isolation + refresh-not-duplicate + already-member-409 + enqueue-once all tested.
- **34 matrix + WS enforcement + 404-vs-403:** the table-driven matrix test pins
  the matrix to the spec table; the WS tests assert non-member join → 4403, viewer
  `update` dropped server-side (doc/persistence/broadcast unchanged) while still
  receiving others' edits, and editor updates apply. The new guard audit (T-1)
  closes the REST hole class.

## Deliberately skipped / deferred

- **Immediate live-socket kick on mid-session revocation** — *deferred*. Spec 29
  exposes no membership-change pub/sub signal, so revocation takes effect on the
  next message/reconnect (documented in ADR 0034). A proactive kick is a feature,
  not a defect — out of scope for a refactor; candidate for a later collab spec.
- **Broad performance work** → **spec 53**. **Structured authz/audit logging** →
  **spec 51**. Neither is a current correctness defect.
- **`AuthorizationService` public API** (spec-34 §5.2 sketched it) — intentionally
  removed rather than wired up: the optimized one-query dependency + `role_for`
  fully cover its responsibilities, and keeping an unused parallel implementation
  was the very "duplicated membership lookup" smell this pass targets. The ADR
  contract is satisfied by `role_for` + `capabilities_for`.
- **F-2 has no paired regression test — deliberate, documented exception.** §5.2
  asks for a test that fails before and passes after "where feasible", and §8 lists
  a regression test per applied backend fix. F-2 is a **no-behaviour-change dead-code
  removal**: the class was never instantiated, so deleting it changes no observable
  behaviour and there is no before/after to assert — a paired regression test is not
  feasible. The surviving single role-lookup path (the dependency's one-query
  `_resolve` + `role_for`) is the *only* path and is already covered by the existing
  authz matrix, WS-enforcement, and guard-coverage tests (T-1). This is the one
  applied fix without a paired test, and it is so by design.

## Migrations / config

None. No data-model change (the `(project_id, user_id, status)` lookup is covered
by spec-33 indexes); no env-var changes.
