# ADR 0008 — Frontend token storage & refresh-on-401

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 09 — Frontend Foundation

## Context

The Inkstave web client is a token-based react-router SPA (no cookies/CSRF, no
SSR). It must hold the spec-07 tokens, attach them to API calls, and keep the
user signed in across navigations and reloads without making token theft easy.

## Decisions

### 1. Access token in memory, refresh token in localStorage

- **Access token: in memory only** (a module variable in `token-store.ts`),
  never written to `localStorage`/`sessionStorage`. Access tokens are
  short-lived (15 min) and the most security-sensitive credential; keeping them
  out of persistent storage removes the easiest XSS exfiltration target.
- **Refresh token: persisted in `localStorage`** (`inkstave.refresh_token`) so a
  full page reload can re-establish a session via `bootstrap()`.

**XSS trade-off (documented):** a refresh token in `localStorage` is readable by
injected scripts. We accept this for the foundation because (a) it is the
simplest approach that survives reloads, and (b) the backend already makes
refresh tokens **server-side revocable with reuse detection** (spec 07), so a
stolen refresh token's blast radius is bounded — using it triggers rotation, and
a replay revokes the whole family. The **hardening option** is an httpOnly,
SameSite refresh cookie (coordinated with backend specs 07/52); that is out of
scope here and noted for later.

### 2. Typed API client with transparent refresh-on-401

`api-client.ts` wraps `fetch`:

- Injects `Authorization: Bearer <accessToken>` from the in-memory store.
- On a `401` (for an authed, non-refresh request), it awaits a **single shared
  in-flight refresh promise** — so N concurrent 401s cause **exactly one**
  `/auth/refresh` call — then **replays the original request once**. A `401` on
  the replay is surfaced (never an infinite loop).
- On refresh failure it **clears the tokens**; the auth context observes the
  clear (via a `token-store` subscription), drops the user, and `<RequireAuth>`
  redirects to `/login`. The decoupling (store event, not imperative
  navigation) keeps the client framework-agnostic and unit-testable.
- Non-2xx responses become a typed `ApiError { status, detail, fieldErrors? }`,
  parsing the project's error envelope — including `422` field errors, which the
  Register form maps to inline messages.

### 3. Auth context + route guards

A React `AuthProvider` exposes `user`, `isAuthenticated`, `isBootstrapping`,
`login()`, `register()`, `logout()`. On load, `bootstrap()` uses a persisted
refresh token to mint an access token and hydrate the user from `/users/me`.
`<RequireAuth>` gates protected routes (redirecting to `/login`, preserving the
intended path); `<PublicOnly>` bounces authenticated users away from
`/login`/`/register`. `logout()` clears local state **even if the network call
fails**.

### 4. UI from shadcn/ui (no hand-rolled controls)

All form controls (`Button`, `Input`, `Label`, `Card`, `Alert`, and the
react-hook-form `Form`) are vendored shadcn/ui components built on Radix +
Tailwind, per the explicit project rule to avoid hand-rolled CSS bugs. Forms use
`react-hook-form` + `zod` whose password/email/match rules mirror the backend so
client and server validation agree.

## Consequences

- New frontend stack: Vite + React 19 + TS (strict) + Tailwind v3 + shadcn/ui +
  react-router v7 + react-hook-form + zod; tooling via ESLint (flat) + Prettier.
- `VITE_API_BASE_URL` configures the backend origin (`frontend/.env.example`).
  The backend `CORS_ORIGINS` default already allows the Vite dev origin
  (`http://localhost:5173`), so no backend change was needed.
- `vite` is pinned to v5 to match `vitest` v2's vite peer (avoids a dual-vite
  type clash).

## Alternatives considered

- **Both tokens in memory** — most secure, but a reload logs the user out; poor
  UX for the foundation. Rejected as the default (it is a valid stricter mode).
- **Refresh token in `localStorage` + access token also persisted** — strictly
  worse (persists the sensitive short-lived token); rejected.
- **httpOnly refresh cookie now** — best XSS posture, but needs cookie/CSRF
  coordination on the backend and complicates the SPA; deferred to a hardening
  spec.
- **A global store (Redux/Zustand)** — unnecessary; React context + a tiny
  token-store module suffices.
