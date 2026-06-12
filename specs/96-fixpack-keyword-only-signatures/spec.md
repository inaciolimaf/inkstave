# Spec 96 — Fix-Pack: Keyword-Only Signatures & Intent-Revealing Methods (requirements)

## 1. Summary

This fix-pack closes **4 confirmed call-site readability/safety issues** found by
a two-reviewer validation pass. Each is a place where a function takes positional
arguments that are easy to mis-order or mis-read at the call site (two adjacent
booleans, three same-shaped ids, four args of which two are `bytes`), or a single
boolean flag that control-couples two distinct intentions into one method. The
fixes are **signature-only**: make the offending parameters keyword-only (and, for
one issue, split a flag into two intention-revealing methods sharing a private
implementation), then update every call site and any test that referenced the old
signature. **No runtime behaviour changes.**

This pack contains **no Overleaf-derived code**: the affected functions are
Inkstave-internal, so there is nothing in the Overleaf reference repo to study.

> **Prerequisite ordering.** This pack edits `auth/refresh_store.py` and
> `collab/store.py`, which **spec 94** also touches (clock injection). **Spec 96
> must be applied after spec 94.** Layer these keyword-only changes on top of
> spec 94's signatures; if `store_refresh` / `snapshot` already gained a clock
> parameter in spec 94, keep it and simply move all multi-arg parameters behind
> the `*` marker as described below.

## 2. Context & dependencies

- **Depends on:** spec 94 (clock injection into `refresh_store.py` and
  `collab/store.py`) — this pack must be applied **after** it. Also the original
  specs that introduced the functions: the auth refresh-token store, the collab
  manager/store, and the CLI seed command.
- **Unlocks:** nothing functional; this is a hardening/cleanup pack.
- **Affected areas:** backend (`cli`, `collab`, `auth`, `services`) and their
  unit tests.

## 3. Goals

- Make the two adjacent booleans of `_cmd_seed` keyword-only and pass them by
  keyword at the call site.
- Replace the `force: bool` control-couple flag on the collab manager's flush
  with two intention-revealing public methods backed by one private helper.
- Make `store_refresh`'s three same-shaped id parameters keyword-only and update
  both call sites.
- Make `snapshot`'s four parameters (two of which are `bytes`) keyword-only and
  update both call sites.
- Keep all behaviour identical and the suite green and under 2 minutes.

## 4. Non-goals (explicitly out of scope)

- No behavioural change of any kind (no new validation, no new branches, no
  changed defaults).
- No edits to files outside §2.
- No broader "make everything keyword-only" sweep — only the four call sites
  listed here.
- No renaming of the underlying private flush implementation's behaviour, only
  its public surface.

## 5. Files in scope

Edit **only** these files.

```
backend/src/inkstave/cli.py
backend/src/inkstave/collab/manager.py
backend/src/inkstave/auth/refresh_store.py
backend/src/inkstave/collab/store.py
backend/src/inkstave/services/auth.py     (call sites of store_refresh only)
backend/tests/unit/                       (tests updated/added to match new signatures live here)
```

If a fix appears to require a file not in this list, **stop and report** rather
than editing it.

## 6. Issues to fix

### 6.1 — `#1` `_cmd_seed` takes two positional booleans (nit · cli)

- **File:** `backend/src/inkstave/cli.py`
- **Problem:** `_cmd_seed(demo: bool, force: bool)` (around line 176) is called
  positionally at line 221 as `_cmd_seed(args.demo, args.force)`. Two adjacent
  positional booleans are unreadable at the call site — a reader cannot tell which
  `True`/`False` means what, and the two are trivially swappable.
- **Fix:** Make both parameters keyword-only:
  `async def _cmd_seed(*, demo: bool, force: bool)`. Update the call site to
  `_cmd_seed(demo=args.demo, force=args.force)`. No other change.

### 6.2 — `#2` `_do_flush_text(..., *, force: bool)` is a control-couple flag (minor · collab)

- **File:** `backend/src/inkstave/collab/manager.py`
- **Problem:** `_do_flush_text(self, document_id, *, force: bool)` (around line
  238) couples two distinct intentions into one boolean:
  - `force=True` → "flush now, unconditionally";
  - `force=False` → "debounced; only flush if the document is dirty".

  The three call sites read ambiguously: `manager.py:119` (`force=True`),
  `manager.py:236` (`force=False`), `manager.py:273` (`force=True`). A reader must
  know what `force` toggles to understand each call.
- **Fix:** Split the public surface into **two intention-revealing methods** that
  share a single private implementation. For example:
  - `async def flush_text_now(self, document_id)` → unconditional flush
    (replaces the old `force=True` calls at lines 119 and 273);
  - `async def flush_text_if_dirty(self, document_id)` → debounced/dirty-only flush
    (replaces the old `force=False` call at line 236).

  Both delegate to a private `_do_flush_text(self, document_id, *, force: bool)`
  (or an equivalently named private helper) that keeps the **exact current logic**.
  Behaviour must be **identical** — only the public method names change. Update the
  three call sites to use the new methods. Keep the private helper's signature
  keyword-only as it already is.

### 6.3 — `#3` `store_refresh` takes three positional same-shaped ids (minor · auth)

- **File:** `backend/src/inkstave/auth/refresh_store.py` (call sites in
  `backend/src/inkstave/services/auth.py`)
- **Problem:** `store_refresh(self, jti, user_id, family_id)` (around line 61)
  takes three positional arguments of similar shape (token/id strings) that are
  easy to mis-order. Call sites pass them positionally at `services/auth.py:81`
  and `services/auth.py:117`.
- **Fix:** Make the three parameters keyword-only:
  `def store_refresh(self, *, jti, user_id, family_id)` (preserve any clock or
  other parameter spec 94 added — place all of these behind the `*`). Update both
  call sites in `services/auth.py` to pass by keyword, e.g.
  `store_refresh(jti=..., user_id=..., family_id=...)`. **In `services/auth.py`,
  only the `store_refresh` call sites may be touched** — do not modify anything
  else in that file.

### 6.4 — `#4` `snapshot` takes four positional args, two are `bytes` (minor · collab)

- **File:** `backend/src/inkstave/collab/store.py` (call sites in
  `backend/src/inkstave/collab/manager.py`)
- **Problem:** `snapshot(self, document_id, state, state_vector, upto_update_id)`
  (around line 63) takes four positional arguments; `state` and `state_vector` are
  both `bytes` and are trivially swappable at a call site with no type error.
  Call sites: `collab/manager.py:103` and `collab/manager.py:262`.
- **Fix:** Make all four parameters keyword-only:
  `def snapshot(self, *, document_id, state, state_vector, upto_update_id)`
  (preserve any clock parameter spec 94 added, also behind the `*`). Update both
  call sites in `manager.py` to pass by keyword. No behavioural change.

## 7. Acceptance criteria

Each is independently verifiable.

1. **`#1`** `_cmd_seed` is declared `async def _cmd_seed(*, demo: bool, force: bool)`;
   the call site reads `_cmd_seed(demo=args.demo, force=args.force)`. A positional
   call (`_cmd_seed(True, False)`) raises `TypeError`.
2. **`#2`** `collab/manager.py` exposes two public flush methods (e.g.
   `flush_text_now` and `flush_text_if_dirty`) delegating to one private helper;
   the old single `force`-flagged **public** entry point is gone. The three former
   call sites (lines ~119, ~236, ~273) now call the matching new method, and the
   flush behaviour is unchanged (existing collab tests pass).
3. **`#3`** `store_refresh` is declared with `*` before `jti, user_id, family_id`
   (plus any spec-94 clock param, also keyword-only). Both call sites in
   `services/auth.py` pass these by keyword; no positional `store_refresh(...)`
   call remains. A positional call raises `TypeError`.
4. **`#4`** `snapshot` is declared with `*` before `document_id, state,
   state_vector, upto_update_id` (plus any spec-94 clock param). Both call sites in
   `manager.py` pass these by keyword; no positional `snapshot(...)` call remains.
   A positional call raises `TypeError`.
5. No positional-argument call to any of the four functions remains anywhere in
   the codebase (`grep` the call sites listed in §6 confirm keyword form / new
   method names).
6. All existing collab / auth / CLI tests pass after updating any test that used
   an old signature; the full suite is green and runs in **< 2 minutes**.

## 8. Test plan

> Keep the combined suite under 2 minutes. No real LaTeX/SMTP/Redis; mock/stub.

- **Stay green:** All existing unit/integration tests for the collab manager and
  store, the refresh store, and the CLI seed command must continue to pass after
  the edits.
- **Update call-site tests:** Any test that called `_cmd_seed`, the collab flush,
  `store_refresh`, or `snapshot` positionally (or invoked the old `force=`
  public flush) must be updated under `backend/tests/unit/` to use the new
  keyword form / new method names. These are mechanical updates, not new coverage.
- **Optional guard (nice-to-have, only if cheap and in-scope):** a tiny unit
  assertion that calling each refactored function positionally raises `TypeError`
  (proves the `*` marker is in place) and that `flush_text_now` /
  `flush_text_if_dirty` both reach the shared private helper. Keep it in-memory
  and fast.
- **Performance/budget note:** This pack adds no slow work; all touched tests are
  in-memory. Run `just test-timed` (xdist) to confirm the budget holds.

## 9. Definition of Done

- [ ] All 4 issues in §6 fixed (signatures changed; call sites and tests updated).
- [ ] All acceptance criteria in §7 pass.
- [ ] Runtime behaviour unchanged (only signatures / public method names changed).
- [ ] Any test referencing an old signature updated and green.
- [ ] Full suite runs in **< 2 minutes** (`just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`, type checker as configured).
- [ ] Edits limited to the files in §5 — no out-of-scope files touched; in
      `services/auth.py` only the `store_refresh` call sites changed.
- [ ] Applied after spec 94; spec-94 clock parameters preserved (kept keyword-only).
- [ ] No Overleaf code copied; stack unchanged.
