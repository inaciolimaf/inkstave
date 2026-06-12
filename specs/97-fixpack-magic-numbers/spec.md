# Spec 97 — Fix-Pack: Magic Numbers in Agent Budget & Section-Locate (requirements)

## 1. Summary

This fix-pack resolves **2 confirmed code-clarity issues** in the server-side AI
agent: unexplained numeric literals in the per-day token/cost **budget** code
(spec 49) and in the deterministic **section-locate** ranking code (spec 48). The
budget module hard-codes seconds-per-day (`86400`) and repeats a 2-day Redis TTL
(`172800`) at two call sites; the locate module hard-codes five scoring thresholds
that encode the match-tier ranking. The fix lifts each into a named, documented
module constant whose value is **numerically identical**, so the duplicated TTL is
derived from one source and the "2-day" / per-tier intent is explicit. **No
behaviour changes:** every budget computation and every locate score/ranking stays
byte-for-byte the same.

> **No Overleaf equivalent.** Neither the agent token/cost budget nor the
> structure-aware section locator exists in Overleaf — Overleaf has no AI agent.
> Both modules are Inkstave-only; there is nothing to study or copy.

## 2. Context & dependencies

- **Depends on:** specs 48 (agent context / section locate) and 49 (agent safety /
  budgets). Both must already be implemented and their tests passing.
- **Unlocks:** nothing functionally — this is a hardening/readability pass. It makes
  the budget window and locate ranking self-documenting for future work in the 40s
  agent specs.
- **Affected areas:** backend only (`agent/safety`, `agent/context`,
  `backend/tests/unit/`).

Edit **only** these files. They are disjoint from all other fix-packs.

```
backend/src/inkstave/agent/safety/budget.py
backend/src/inkstave/agent/context/locate.py
backend/tests/unit/                       (new/updated unit test files may be added here)
```

If a fix appears to require another file, **stop and report** — do not reach
outside this set. (In particular, surfacing the TTL via the agent settings group is
*optional*; if it cannot be done without editing a settings file outside this set,
keep the TTL as a documented module constant instead — see §5.1.)

## 3. Goals

- Replace the `86400` and the two `172800` literals in `budget.py` with named
  constants, deriving the 2-day TTL from a single seconds-per-day source so the
  duplication is gone.
- Replace the five scoring thresholds in `locate.py` with named, per-tier
  constants documented with the ranking rationale.
- Keep every value numerically identical; no behaviour change.

## 4. Non-goals (explicitly out of scope)

- Retuning any budget window or locate score (values are frozen).
- Changing the Redis key layout, the TTL duration, or the day-bucket math.
- Changing the locate match tiers, their order, or the rounding of the
  token-overlap score.
- Editing any file outside §2 (including settings/config modules, unless a settings
  home for the TTL can be added **without** leaving the in-scope set — see §5.1).
- Adding new env vars or features.

## 5. Detailed requirements

### 5.1 `agent/safety/budget.py` — named budget constants (replaces `#magic-budget`)

- **File:** `backend/src/inkstave/agent/safety/budget.py`
- **Problem:** Three business-meaning literals are unexplained and one is duplicated:
  - line 53: `return int(now) // 86400` — `86400` is **seconds per day**, used to
    bucket usage counters into a daily key.
  - line 97: `await redis.expire(tkey, 172800)` — `172800` is a **2-day TTL**
    (in seconds) on the per-project daily token counter.
  - line 100: `await redis.expire(ckey, 172800)` — the **same** 2-day TTL on the
    per-user daily cost counter, repeated.

  The `172800` is a duplicated literal with no stated relationship to the day
  bucket, and its "2 days" intent (one extra day of grace past the day bucket) is
  invisible.
- **Fix:** Introduce named module-level constants near the top of the module
  (alongside `_DEFAULT_RATE`), with short comments, e.g.:

  ```python
  _SECONDS_PER_DAY = 86_400  # day-bucket granularity for per-day usage counters
  # Daily counters live one extra day past their bucket so late roll-ups still land.
  _BUDGET_KEY_TTL_SECONDS = 2 * _SECONDS_PER_DAY  # == 172_800 (2-day grace TTL)
  ```

  Then:
  - Use `_SECONDS_PER_DAY` in `_day(now)`:
    `return int(now) // _SECONDS_PER_DAY`.
  - Use `_BUDGET_KEY_TTL_SECONDS` at **both** `expire(...)` call sites
    (lines 97 and 100), eliminating the `172800` duplication — it is now derived
    from one source.

  **Optional settings home:** if (and only if) the agent settings group can take a
  TTL field **without editing any file outside §2**, you may instead read the TTL
  from `settings` (default `2 * _SECONDS_PER_DAY`). Because `record_usage` does not
  currently receive `settings`, adding a parameter or a settings import would change
  call sites outside scope; therefore the **default and expected** resolution is the
  documented module constant. Do not widen scope to surface it via settings.

  The constant **must** evaluate to exactly `172800` (and `86_400` for the day
  granularity). Naming may differ but must be a leading-underscore module constant
  consistent with the existing `_DEFAULT_RATE` style.

### 5.2 `agent/context/locate.py` — named scoring-tier constants (replaces `#magic-locate`)

- **File:** `backend/src/inkstave/agent/context/locate.py`
- **Problem:** Five scoring thresholds are inline literals that encode the
  section-match **ranking tiers** but carry no name or rationale:
  - line 73: `score=0.92` — an **ordinal** match ("section 2", "the first
    subsection"), resolved in `_ordinal_match`.
  - line 98: `score, reason = 0.95, "label"` — an exact **label** (`\label{...}`)
    match.
  - line 100: `score, reason = 0.9, "synonym"` — a **synonym** concept appears in
    the title.
  - line 102: `score, reason = 0.7, "substring"` — the query is a **substring** of
    the title (or vice-versa).
  - line 106: `round(overlap * 0.6, 3)` — a **token-overlap** multiplier scaling
    the fraction of shared tokens.

  (The exact-title score `1.0` at line 96 is a self-evident "perfect match"
  sentinel; it may be left as-is or named for consistency — naming it is optional
  and at the implementer's discretion, but if named it must remain `1.0`.)
- **Fix:** Lift the five thresholds into named module-level constants near the top
  of the module (alongside `_SYNONYMS` / `_ORDINALS`), each with a one-line comment
  explaining its tier and why it ranks where it does, ordered from strongest to
  weakest, e.g.:

  ```python
  # Section-match score tiers, strongest → weakest. Higher wins on ties.
  _SCORE_LABEL_MATCH = 0.95     # exact \label{...} match — near-certain intent
  _SCORE_ORDINAL = 0.92         # positional match e.g. "section 2" / "first subsection"
  _SCORE_SYNONYM = 0.9          # a known synonym concept appears in the title
  _SCORE_SUBSTRING = 0.7        # query is a substring of the title (or vice-versa)
  _SCORE_TOKEN_OVERLAP = 0.6    # multiplier on the shared-token fraction (fuzzy fallback)
  ```

  Then reference each constant where its literal currently appears:
  - `_ordinal_match` → `score=_SCORE_ORDINAL`.
  - label branch → `score, reason = _SCORE_LABEL_MATCH, "label"`.
  - synonym branch → `score, reason = _SCORE_SYNONYM, "synonym"`.
  - substring branch → `score, reason = _SCORE_SUBSTRING, "substring"`.
  - token-overlap branch → `round(overlap * _SCORE_TOKEN_OVERLAP, 3)`.

  Every constant **must** keep its exact value so each match's `score` and the final
  `matches.sort(...)` ordering are unchanged.

### 5.3 Configuration

No new env vars and no config changes are required. The budget TTL stays a
documented module constant (see §5.1); only surface it via settings if that is
possible without editing a file outside §2 (it is not, by default — so leave it).

## 6. Overleaf reference (study only — never copy)

> **None.** The AI agent's token/cost budget (`agent/safety/budget.py`) and the
> structure-aware section locator (`agent/context/locate.py`) have **no Overleaf
> equivalent** — Overleaf ships no AI agent. There is nothing to read or adapt;
> implement strictly from this spec and the existing Inkstave code.

## 7. Acceptance criteria

Each is independently verifiable.

1. **`budget.py` day bucket** `int(now) // _SECONDS_PER_DAY` is used in `_day`, and
   `_SECONDS_PER_DAY == 86400`. No bare `86400` literal remains in `budget.py`.
2. **`budget.py` TTL derived once** A single source defines the 2-day TTL
   (`_BUDGET_KEY_TTL_SECONDS == 172800`, derived as `2 * _SECONDS_PER_DAY`), and
   both `redis.expire(...)` calls reference it. No bare `172800` literal remains in
   `budget.py` (`grep -c '172800' backend/src/inkstave/agent/safety/budget.py`
   returns `0`).
3. **`locate.py` scoring constants** The five thresholds are named module constants
   (`_SCORE_LABEL_MATCH == 0.95`, `_SCORE_ORDINAL == 0.92`, `_SCORE_SYNONYM == 0.9`,
   `_SCORE_SUBSTRING == 0.7`, `_SCORE_TOKEN_OVERLAP == 0.6`) and are referenced at
   the five sites; no bare `0.95`/`0.92`/`0.9`/`0.7`/`0.6` scoring literals remain
   in the matching code at lines ~73 and ~98–106.
4. **Values identical** All budget computations (`_day`, `precheck_day`,
   `record_usage` including the TTL set on both keys) and all `locate_section`
   scores and ranking order are unchanged from before the edit.
5. **Tests green** The existing agent budget and section-locate unit tests pass
   **unchanged** (no test had to be modified to accommodate a value change).
6. The full test suite is green and runs in **< 2 minutes** (verified via
   `just test-timed`).

## 8. Test plan

> Keep the combined suite under 2 minutes. No real LLM/Redis; the existing tests
> already use fakes/stubs. All new assertions are pure in-memory checks.

- **Stay green:** All existing unit tests for the agent budget enforcement
  (`precheck_day` / `record_usage` / `run_tokens_exceeded` / `run_cost_exceeded`)
  and for section-locate ranking (`locate_section`) must continue to pass **without
  modification** — proving behaviour is unchanged.
- **New / updated guard tests (small, in `backend/tests/unit/`):**
  - Assert the derived TTL equals the original literal:
    `_BUDGET_KEY_TTL_SECONDS == 172800` and `_SECONDS_PER_DAY == 86400` (import the
    module constants). This locks the "no value drift" invariant.
  - Optionally assert each locate score constant equals its prior value
    (`_SCORE_LABEL_MATCH == 0.95`, etc.) and/or run `locate_section` over a small
    sample `ProjectMap` and assert the produced scores and the resulting ranking
    order are exactly as before (e.g. a label match outranks a synonym match
    outranks a substring match).
  - If `record_usage` is exercised with a fake Redis (as in the existing budget
    test), assert `expire` was called with `172800` on both the project-token and
    user-cost keys — confirming the constant is wired to both sites.
- **Performance/budget note:** All assertions are constant comparisons or a single
  in-memory `locate_section` call over a tiny outline; they add negligible time and
  do **not** affect the 2-minute budget.

## 9. Definition of Done

- [ ] Both issues in §5 fixed (named constants introduced; `86400` and the
      duplicated `172800` removed from `budget.py`; the five locate thresholds
      named in `locate.py`).
- [ ] All acceptance criteria in §7 pass.
- [ ] New/updated guard tests in §8 written and green; existing budget/locate tests
      pass unchanged.
- [ ] Full suite runs in **< 2 minutes** (`just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`, type checker as configured).
- [ ] Edits limited to the files in §2 — no out-of-scope files touched; no env/config
      changes.
- [ ] No Overleaf code copied (there is no Overleaf equivalent); stack unchanged.
