# Spec 10 — Refactor: Auth & Frontend Foundation

**Type:** 🔧 refactor  ·  **Phase:** Auth & users  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing a **refactoring** spec — it adds **no features**. Do this:

1. **Read the requirements.** The full process and acceptance bar are in
   [`spec.md`](spec.md). Follow it exactly.
2. **Confirm prerequisites.** This spec depends on **06, 07, 08, 09** being fully
   implemented with green tests. If any earlier spec's tests are red, stop and
   fix that first — do not refactor on top of a broken base.
3. **Scan, don't rewrite.** Systematically review the auth backend (model,
   hashing, tokens, refresh store, guards, rate-limit groundwork, endpoints) and
   the frontend foundation (API client, token storage, auth context, pages) for
   bugs, code smells, **security issues** (token handling, timing attacks,
   secret/PII leakage, error-message enumeration), and missing tests.
4. **Judge each finding (risk vs. value).** Apply the worthwhile, low-risk,
   high-value fixes. Defer or skip the rest with a written reason. **No behaviour
   changes** that alter the public contracts of specs 06–09.
5. **Keep tests green** at every step; add tests for any gap you find (especially
   security-relevant ones). Keep the full suite under 2 minutes.
6. **Produce a changelog** of what was applied vs. deliberately skipped, and run
   the security checklist in `spec.md`.

There is **no Overleaf reference** for this spec.

When all Definition-of-Done items pass, this spec is complete. Move to spec 11.

## One-line goal

The auth backend and frontend foundation are measurably cleaner, safer, and
better-tested — with identical externally-observable behaviour.

## Do NOT (scope guard)

- Do not add new features or new endpoints; do not change request/response
  contracts, status codes, or token semantics established in 06–09.
- Do not introduce new technologies or dependencies unless a fix strictly
  requires it (justify in the changelog).
- Do not refactor code outside the auth + frontend-foundation surface (specs
  01–05 foundations are out of scope unless a fix is trivially local and clearly
  justified).
- Do not let the test suite go red or exceed the 2-minute budget.
