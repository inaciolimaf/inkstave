# Spec 94 — Fix-Pack: Injectable Clock for Auth Time Logic (requirements)

## 1. Summary

The security audit found ~12 direct `datetime.now(UTC)` call sites across the
codebase. Several of them sit in **security-critical auth paths** — JWT access /
refresh token `iat`/`exp` claims, refresh-token rotation and family revocation
cutoffs, and the email-change token expiry — where they make boundary and
clock-skew behaviour impossible to test without real wall-clock time passing.

This fix-pack introduces a tiny **injectable `Clock` abstraction** and threads it
through **only those highest-value auth seams**, so expiry edge cases are
deterministically testable with a `FrozenClock`. Production call sites keep their
exact current behaviour by defaulting to the system clock. The remaining
(non-auth) `datetime.now(UTC)` sites are explicitly recorded as a follow-up in §4
and are **out of scope** here, to keep this pack small and low-risk.

There is **no Overleaf equivalent** for this seam: token/clock injection is an
Inkstave implementation detail with no counterpart in the Overleaf reference.

## 2. Context & dependencies

- **Depends on:** specs **92** and **93** (final form of the auth token files and
  `services/account.py`), and all earlier auth specs that introduced
  `auth/tokens.py`, `auth/refresh_store.py`, and `services/account.py`.
- **Prerequisite ordering:** This pack edits `services/account.py` (also touched
  by spec 93) and the auth token files (`auth/tokens.py`, `auth/refresh_store.py`,
  also touched by specs 92 and 93). It **must be applied AFTER specs 92 and 93**
  so it builds on their committed versions of those files.
- **Unlocks:** deterministic time-based testing of the auth surface; a reusable
  `Clock`/`FrozenClock` seam later packs can extend to the non-auth sites in §4.
- **Affected areas:** backend only.

## 3. Files in scope

Edit **only** these files. Apply the pack after specs 92 and 93.

```
backend/src/inkstave/time.py            (NEW — the Clock abstraction)
backend/src/inkstave/auth/tokens.py
backend/src/inkstave/auth/refresh_store.py
backend/src/inkstave/services/account.py
backend/tests/unit/                     (new/updated unit tests + a FrozenClock helper)
```

> Pick **one** module name for the abstraction — `backend/src/inkstave/time.py`
> (preferred) **or** `clock.py` — and be consistent across imports. Do **not**
> create both. (`time.py` shadows the stdlib module name only at the package
> level `inkstave.time`, which is unambiguous; if that is a concern in the local
> style, use `clock.py` instead — but choose one.)

If a fix appears to require another file, **stop and report** rather than reaching
outside this set.

## 4. Non-goals (explicitly out of scope — documented follow-up)

This pack **intentionally** does not touch the other `datetime.now(UTC)` sites the
audit found. They are recorded here as a **follow-up**, not part of this pack:

- `backend/src/inkstave/collab/store.py:75`
- `backend/src/inkstave/compile/retention.py:20`
- `backend/src/inkstave/agent/api/cleanup.py:29`
- `backend/src/inkstave/notifications/invite_hook.py:58`
- `backend/src/inkstave/history/capture.py:122`
- `backend/src/inkstave/history/capture.py:298`
- `backend/src/inkstave/agent/api/events.py:40`
- `backend/src/inkstave/agent/runner.py:142`

These are lower-risk (retention sweeps, audit cleanup, history timestamps, event
emission) and are deliberately deferred. A later pack may migrate them to the same
`Clock` seam introduced here. **Do not edit them in this pack.**

Also out of scope: changing token lifetimes/algorithms, altering rotation policy,
adding new endpoints, or wiring the `Clock` through FastAPI dependency injection
at the route layer (the functions take a defaulted parameter; route wiring is not
required).

## 5. Detailed requirements

### 5.1 The `Clock` abstraction (NEW — `backend/src/inkstave/time.py`)

Create a minimal module exposing:

- A **`Clock` Protocol** (or small ABC) with a single method
  `now() -> datetime` that **must** return a timezone-aware UTC `datetime`.
- A **`SystemClock`** implementation whose `now()` returns `datetime.now(UTC)`
  — i.e. it wraps exactly the call the auth code uses today, so default behaviour
  is byte-for-byte equivalent.
- A **module-level default instance** (e.g. `SYSTEM_CLOCK = SystemClock()`) that
  the auth functions default to when no clock is supplied.

**Precedent to follow:** the codebase already injects a clock via context in
`backend/src/inkstave/agent/api/jobs.py:81`. Mirror that pattern's shape and
naming intent for consistency rather than inventing a new convention. Keep the
abstraction tiny — one method, no scheduling, no monotonic time, no async.

A **`FrozenClock`** test helper (fixed time, with the ability to advance) lives in
the **tests** tree (§5.5), not in production code.

### 5.2 `auth/tokens.py` — inject `now` into token creation

- **File:** `backend/src/inkstave/auth/tokens.py`
- **Lines (reference):** ~44 and ~58 — `datetime.now(UTC)` is called directly to
  compute the `iat` and `exp` claims of the access and refresh tokens.
- **Requirement:** The token-creation function(s) must accept an **injected time**
  so that expiry / clock-skew / boundary cases are testable without real time
  passing. Accept either a `Clock` or a `datetime` (pick one shape and apply it
  consistently across both functions), defaulting to the system clock
  (`SYSTEM_CLOCK` / `SystemClock().now()`). When no argument is supplied, the
  computed `iat`/`exp` must be **identical** to today's behaviour.
- Compute the "now" value **once** per call (do not call the clock twice for
  `iat` and `exp`); derive `exp = now + lifetime` from that single reading.

### 5.3 `auth/refresh_store.py` — inject `now` into store / revoke

- **File:** `backend/src/inkstave/auth/refresh_store.py`
- **Lines (reference):** ~71 (in `store_refresh`) and ~114 (in `revoke_user`) —
  `datetime.now(UTC)` is used for timestamps / cutoffs.
- **Requirement:** `store_refresh` and `revoke_user` must take their "now" from an
  **injected clock / `now` parameter** (default system clock) so token rotation
  and family-revocation boundaries are deterministically testable. Default
  behaviour with no argument must be unchanged. Use the same injection shape
  chosen in §5.2 for consistency.

### 5.4 `services/account.py` — inject `now` into email-change expiry

- **File:** `backend/src/inkstave/services/account.py`
- **Lines (reference):** ~95 (in `start_email_change`, setting the token expiry)
  and ~108 (in `confirm_email_change`, checking the expiry) — both call
  `datetime.now(UTC)` directly.
- **Requirement:** Inject the clock / `now` into both functions so the
  email-change token expiry edge cases (exactly-at-expiry, just-after-expiry) are
  testable. Default to the system clock; unchanged behaviour when no argument is
  supplied. Use the same injection shape chosen in §5.2/§5.3.

### 5.5 Test helper — `FrozenClock`

- Provide a `FrozenClock` helper in the **tests** tree (e.g. a small
  `backend/tests/unit/_clock.py` or a fixture/conftest helper under
  `backend/tests/unit/`). It satisfies the `Clock` Protocol, returns a **fixed**
  timezone-aware UTC `datetime`, and exposes a way to **advance** it (e.g.
  `advance(seconds=...)` or `set(dt)`), so a test can step time across a token's
  `exp` boundary without sleeping.

### 5.6 Configuration

No new env vars, config files, or feature flags. The `Clock` is a code-level
injection seam with a system-time default.

## 6. Overleaf reference (study only — never copy)

> There is **no Overleaf equivalent** for this seam. Token expiry / clock
> injection is an Inkstave implementation detail; the Overleaf reference has no
> corresponding abstraction to study. Implement from this spec and the existing
> in-repo precedent at `backend/src/inkstave/agent/api/jobs.py:81`.

## 7. Acceptance criteria

Each is independently verifiable.

1. A `Clock` abstraction exists in **one** new module
   (`inkstave/time.py` *or* `inkstave/clock.py`, not both): a `Clock`
   Protocol/ABC with `now() -> datetime`, a `SystemClock` wrapping
   `datetime.now(UTC)`, and a module-level default instance.
2. A `FrozenClock` test helper exists in the tests tree, returns a fixed
   tz-aware UTC time, and can be advanced.
3. `auth/tokens.py` token creation accepts an injected time and, with **no**
   argument, produces `iat`/`exp` identical to the previous behaviour.
4. `auth/refresh_store.py` `store_refresh` and `revoke_user` take their time from
   an injected clock/`now` (default system clock); defaults unchanged.
5. `services/account.py` `start_email_change` and `confirm_email_change` inject
   the clock/`now` for setting and checking email-change expiry; defaults
   unchanged.
6. A unit test using `FrozenClock` deterministically asserts a token is **not**
   expired just before its `exp` and **is** expired exactly at / after its `exp`,
   **without any real sleep**.
7. A unit test using `FrozenClock` proves the refresh-rotation cutoff and the
   email-change-token expiry behave deterministically at the boundary.
8. All production call sites compile and behave **identically by default**
   (existing auth/account tests stay green with no expectation changes for the
   default-clock path).
9. The non-auth `datetime.now(UTC)` sites listed in §4 are **untouched** by this
   pack.
10. The full test suite is green and runs in **< 2 minutes** (`just test-timed`).

## 8. Test plan

> Keep the combined suite under 2 minutes. No real sleeps — use `FrozenClock`.

- **Stay green:** All existing auth / token / refresh-store / account tests must
  continue to pass after the edits, exercising the default (system-clock) path
  with no changed expectations.
- **New unit tests (in `backend/tests/unit/`, using `FrozenClock`):**
  - **Token expiry boundary** (`auth/tokens.py`): create a token at a frozen
    `t0`; with the clock still at `t0 + lifetime - ε` the token validates; at
    exactly `t0 + lifetime` (and `+ε`) it is expired. Also assert that creating a
    token with **no** injected clock yields the same `exp - iat` lifetime as
    before (defaults unchanged).
  - **Refresh rotation cutoff** (`auth/refresh_store.py`): drive `store_refresh` /
    `revoke_user` with a `FrozenClock` and assert the stored timestamp / revocation
    cutoff is computed from the injected time, and that rotation/family-revocation
    boundaries fall on the expected side of the cutoff. Mock the underlying
    store/Redis so no real backend is needed.
  - **Email-change expiry** (`services/account.py`): with a `FrozenClock`, set an
    email-change token at `t0`; confirm succeeds just before expiry and fails
    exactly at / after expiry. Use mocked repositories/hashers — no DB.
  - **Defaults unchanged:** for each of the three modules, a test (or assertion)
    that calling the function with no clock argument matches the prior behaviour.
- **Integration:** none required; this is a code-seam pack. Existing integration
  tests covering login/refresh/email-change must stay green unchanged.
- **E2E:** not applicable.
- **Performance/budget note:** All new tests are in-memory and use `FrozenClock`
  instead of `asyncio.sleep` / real time, so they are effectively instant and
  *remove* a class of potential time-based flakiness. Run `just test-timed`
  (xdist) to confirm the budget.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (single new `Clock` module; `now`
      injected into `auth/tokens.py`, `auth/refresh_store.py`, and the two
      `services/account.py` email-change functions; `FrozenClock` test helper).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green; new tests use `FrozenClock`, no sleeps.
- [ ] Default behaviour is byte-for-byte unchanged when no clock is supplied.
- [ ] The §4 non-auth sites are untouched; edits limited to the §3 file set.
- [ ] Applied **after** specs 92 and 93.
- [ ] Full suite runs in **< 2 minutes** (`just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`, type checker as configured).
- [ ] No new env vars (none required); no Overleaf code copied; stack unchanged.
