# Spec 09 — Frontend Foundation

**Type:** 🟢 feature  ·  **Phase:** Auth & users  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **02** (backend app runs,
   CORS configurable) and **04** (Vitest + Playwright testing foundation). The
   backend auth endpoints from **06–08** (`/auth/register`, `/auth/login`,
   `/auth/refresh`, `/auth/logout`, `/users/me`) must exist so the UI can wire to
   them. Confirm those are implemented and green before wiring against them.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md`. **Do not copy or translate any
   Overleaf code.** Note: Overleaf renders pages server-side (Pug) with React
   islands and uses CSRF-token + cookie sessions; Inkstave is a token-based SPA
   with react-router. Study only the **fetch-wrapper / API-call ergonomics** and
   the **auth-context** idea, then write your own.
4. **Implement** the Vite + React + TS + Tailwind + shadcn/ui app: routing, the
   typed API client (in-memory access token + refresh-on-401), the auth
   context/store, and login / register / logout pages using **ready-made shadcn
   components**, plus a protected-route wrapper, env config, and ESLint/Prettier.
5. **Write the tests** listed in the spec's Test plan (Vitest unit/component +
   one Playwright e2e auth flow against a mocked or real backend).
6. **Verify.** Run the full suite (< 2 minutes); check every Acceptance criterion
   and Definition-of-Done item.
7. **Record decisions.** Add an ADR under `docs/` for token storage (in-memory
   access token + how refresh is held) and the refresh-on-401 strategy.

When all Definition-of-Done items pass, this spec is complete. Move to spec 10.

## One-line goal

A user can open the Inkstave web app, register, log in, see a protected page,
and log out — with the access token kept in memory and silently refreshed on
401.

## Do NOT (scope guard)

- Do not build the project dashboard, file tree, editor, or any post-auth feature
  UI — those are Phase 2+ specs. A minimal placeholder protected page is enough.
- Do not hand-roll bespoke CSS for form controls/buttons/inputs — use shadcn/ui
  components to avoid CSS bugs (this is an explicit project rule).
- Do not copy Overleaf source code or its CSRF/session model.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`):
  Vite/React/TS/Tailwind/shadcn/ui, react-router, Vitest, Playwright.
