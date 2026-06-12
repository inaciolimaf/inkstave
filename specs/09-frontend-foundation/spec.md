# Spec 09 — Frontend Foundation (requirements)

## 1. Summary

This spec stands up the Inkstave web client: a Vite + React + TypeScript +
Tailwind + shadcn/ui single-page app with react-router, a typed API client that
holds the access token **in memory** and transparently refreshes it on a `401`,
an auth context/store, and the **register / login / logout** pages plus a
protected-route wrapper and a minimal protected landing page. It establishes the
frontend conventions (structure, tooling, component usage) every later UI spec
follows. It wires to the auth backend from specs 06–08.

## 2. Context & dependencies

- **Depends on:** spec **02** (backend reachable; CORS configurable for the dev
  origin), spec **04** (Vitest + React Testing Library + Playwright configured),
  and the auth endpoints from **06–08**.
- **Unlocks:** every frontend feature spec (dashboard 16, file tree 17, editor
  18, …) — they reuse this app shell, API client, and auth context.
- **Affected areas:** frontend (new app), infra (frontend dev config, CORS env on
  backend if not already present), docs (token-storage ADR).

## 3. Goals

- A working Vite/React/TS app under `frontend/` with Tailwind and shadcn/ui
  initialised; strict TypeScript; ESLint + Prettier configured and clean.
- react-router routing with public routes (`/login`, `/register`) and protected
  routes behind a `<RequireAuth>` wrapper (`/` landing).
- A typed API client (`fetch` wrapper) that:
  - injects `Authorization: Bearer <accessToken>` from in-memory state,
  - on `401`, calls `/auth/refresh` **once**, updates tokens, and **replays** the
    original request; if refresh fails, clears auth and redirects to `/login`,
  - de-duplicates concurrent refreshes (a single in-flight refresh shared by all
    waiting requests),
  - returns typed results and a typed `ApiError`.
- An auth context/store exposing `user`, `isAuthenticated`, `login()`,
  `register()`, `logout()`, and `bootstrap()` (hydrate from `/users/me` on app
  load if a refresh token is available).
- Login, Register, and Logout flows built from **shadcn/ui** components
  (`Form`, `Input`, `Button`, `Card`, `Label`, `Alert`/`toast`) with client-side
  validation, loading and error states.
- Environment-based API base URL config.

## 4. Non-goals (explicitly out of scope)

- Any post-auth product UI (projects/editor/etc.) beyond a placeholder landing
  page showing the logged-in user's name and a logout button.
- Email-confirmation, password-reset, profile/settings UI (spec 59 and later).
- SSR / server rendering (Inkstave client is a SPA).
- A global state library beyond React context + a small module (no Redux/Zustand
  required; if a tiny store helper is used, keep it minimal and documented).
- Theming/dark-mode polish (basic shadcn theme is fine).

## 5. Detailed requirements

### 5.1 Data model

None (frontend). The client mirrors backend Pydantic shapes as TS types:

- `UserPublic`: `{ id: string; email: string; display_name: string;
  is_admin: boolean; email_confirmed: boolean; created_at: string }`.
- `TokenPair`: `{ access_token: string; refresh_token: string;
  token_type: "bearer"; expires_in: number }`.

### 5.2 Backend / API

No new backend endpoints. The frontend consumes:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | create account → `UserPublic` (then auto-login or redirect to login — see UI) |
| POST | `/api/v1/auth/login` | → `TokenPair` |
| POST | `/api/v1/auth/refresh` | → `TokenPair` |
| POST | `/api/v1/auth/logout` | revoke refresh |
| GET | `/api/v1/users/me` | → `UserPublic` (bootstrap/hydrate) |

If CORS for the dev origin is not already configured in spec 02, add the dev
origin to the backend `CORS_ORIGINS` env and document it.

### 5.3 Frontend / UI

#### App structure (suggested, follow project conventions once set)

```
frontend/
├── index.html
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.* / postcss
├── components.json            # shadcn/ui config
├── .eslintrc.* / .prettierrc
└── src/
    ├── main.tsx               # router + providers mount
    ├── App.tsx                # <RouterProvider> / route tree
    ├── lib/
    │   ├── api-client.ts      # typed fetch wrapper + refresh-on-401
    │   └── token-store.ts     # in-memory access token + refresh handling
    ├── auth/
    │   ├── auth-context.tsx   # provider + useAuth()
    │   └── require-auth.tsx   # <RequireAuth> route guard
    ├── pages/
    │   ├── login.tsx
    │   ├── register.tsx
    │   └── home.tsx           # placeholder protected page
    ├── components/ui/         # shadcn-generated components
    └── config.ts              # reads import.meta.env
```

#### Routing (react-router)

- `/login` → Login page (public; if already authenticated, redirect to `/`).
- `/register` → Register page (public; same redirect-if-authed).
- `/` → Home (protected by `<RequireAuth>`).
- Unknown route → redirect to `/` (or a simple 404). `<RequireAuth>` redirects
  unauthenticated users to `/login`, preserving the intended path for post-login
  return (optional but recommended).

#### Token storage & refresh (token-store + api-client)

- **Access token: in memory only** (a module variable / context), never in
  `localStorage` (XSS-exfiltration risk). Document this in the ADR.
- **Refresh token:** for this spec, the simplest acceptable approach is to keep
  the refresh token in memory too (lost on full reload → user must log in again),
  OR persist it in `localStorage` to survive reloads. **Default:** persist the
  refresh token in `localStorage` and access token in memory; on app load,
  `bootstrap()` uses the stored refresh token to obtain a fresh access token and
  then calls `/users/me`. Clearly document the XSS trade-off and note that an
  httpOnly-cookie refresh token is a hardening option (coordinated with backend
  spec 07/52) — out of scope here.
- `api-client`:
  - Adds the `Authorization` header when an access token exists.
  - On `401` (and only when not already a refresh call): await a **shared**
    `refreshPromise` (create one if none in flight) that calls `/auth/refresh`;
    on success, store new tokens and **retry the original request once**; on
    failure, clear tokens, set `isAuthenticated=false`, and bounce to `/login`.
  - Never loops infinitely (retry at most once per request; a `401` on the retry
    propagates as `ApiError`).
  - Surfaces non-2xx as a typed `ApiError { status, detail, fieldErrors? }`,
    parsing the backend error envelope (incl. `422` field errors for forms).

#### Pages (use shadcn/ui — do not hand-roll inputs/buttons)

- **Register page:** `Card` containing a `Form` with `email`, `password`,
  `confirm password`, `display name` fields (`Input` + `Label`), a submit
  `Button` with a loading spinner state, and inline field errors mapped from the
  backend `422`. Client-side validation (zod + react-hook-form via shadcn `Form`
  is recommended): required fields, email format, password 8–72 with letter+digit
  (mirror backend rules so the UX matches), passwords match. On success: either
  auto-login (call login, then redirect to `/`) or redirect to `/login` with a
  success toast — **default: redirect to `/login` with a success message** (keeps
  it simple; auto-login is acceptable if implemented cleanly). Duplicate email
  (`409`) shows a non-field `Alert`.
- **Login page:** `Card` + `Form` with `email`, `password`, submit `Button`.
  On success store tokens, set user, redirect to `/` (or the saved return path).
  On `401` show "Invalid email or password." in an `Alert` (do not reveal which
  field). On `429` show a "too many attempts, try again later" message.
- **Logout:** a `Button` (in the Home page header) that calls `/auth/logout`,
  clears in-memory + stored tokens, and redirects to `/login`. Logout must
  succeed for the user even if the network call fails (clear local state
  regardless).
- **Home (placeholder):** shows `Welcome, {display_name}` and the logout button;
  proves the protected route + bootstrap work. No further features.

#### States & a11y

- Every async action has explicit **loading**, **error**, and **success** states
  (disabled buttons + spinners; error `Alert`/`toast`). Forms are keyboard-
  navigable; inputs have associated `Label`s; error messages are announced
  (`aria-live`/shadcn defaults). No layout shift on error display.

### 5.4 Real-time / jobs / external integrations

None. (WebSocket usage arrives in the realtime specs; this spec only consumes
REST.)

### 5.5 Configuration

Frontend env (Vite, `VITE_` prefix), documented in `.env.example` (and/or a
`frontend/.env.example`):

| Var | Default (dev) | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend origin/base for the API client. |

Backend (only if not already set in spec 02):

| Var | Default | Purpose |
| --- | --- | --- |
| `CORS_ORIGINS` | `http://localhost:5173` | Allow the Vite dev origin (and prod origin later). |

Tooling: ESLint (typescript-eslint, react, react-hooks) + Prettier; `tsconfig`
with `strict: true`. `npm run lint`, `npm run typecheck`, `npm run test`,
`npm run build` all succeed.

## 6. Overleaf reference (study only — never copy)

> Read in `../overleaf/`. Inkstave is a token-based react-router SPA; Overleaf
> server-renders Pug pages with React islands and uses CSRF + cookie sessions.
> Study only the ergonomics noted below.

- `services/web/frontend/js/infrastructure/fetch-json.ts` — the `getJSON` /
  `postJSON` / `putJSON` / `deleteJSON` wrapper ergonomics, typed return values,
  and a `FetchError` carrying status/body. Inkstave's `api-client` mirrors this
  *shape* but adds Bearer injection + refresh-on-401 (Overleaf has no JWT; it
  uses the `X-Csrf-Token` header — **do not** copy the CSRF approach).
- `services/web/frontend/js/shared/context/user-context.tsx` — how a current-user
  context is exposed to the React tree. Inkstave builds its own `auth-context`
  that additionally manages tokens.
- `services/web/frontend/js/shared/components/` and `.../shared/hooks/` — general
  approach to shared components/hooks organisation (structure only). Inkstave
  uses shadcn/ui components instead of Overleaf's component library.
- Note: Overleaf has **no react-router top-level router** (it routes via the
  server). There is no Overleaf equivalent for Inkstave's SPA router or its
  in-memory-token + refresh-on-401 client — those are Inkstave's own design.

## 7. Acceptance criteria

1. **Given** the app at `/` while unauthenticated, **when** it loads, **then**
   `<RequireAuth>` redirects to `/login`.
2. **Given** the Register page, **when** I submit a valid email, a compliant
   password (matched in both fields), and a display name, **then** the request
   succeeds and I land on `/login` with a success message (or am auto-logged-in
   and land on `/`, per the chosen default).
3. **Given** the Register page, **when** I submit mismatched passwords or an
   invalid email, **then** client-side validation blocks submission and shows
   inline field errors; **when** the backend returns `409` (duplicate), **then** a
   non-field error `Alert` appears.
4. **Given** the Login page with valid credentials, **when** I submit, **then**
   tokens are stored (access in memory), the auth context shows the user, and I
   am redirected to `/`, which displays `Welcome, {display_name}`.
5. **Given** valid credentials are wrong, **when** I submit login, **then** I see
   "Invalid email or password." and remain on `/login`.
6. **Given** I am authenticated and my access token has expired, **when** I make
   an API call that returns `401`, **then** the client silently calls
   `/auth/refresh`, replays the request once, and the call succeeds without the
   user noticing; **when** refresh also fails, **then** I am logged out and sent
   to `/login`.
7. **Given** two API calls fire concurrently and both receive `401`, **then**
   only **one** `/auth/refresh` request is made (shared in-flight promise) and
   both original requests are replayed.
8. **Given** I am on `/` authenticated, **when** I click Logout, **then**
   `/auth/logout` is called, local + stored tokens are cleared, and I am
   redirected to `/login` (and clearing happens even if the network call fails).
9. **Given** a full page reload while authenticated (refresh token persisted),
   **when** the app boots, **then** `bootstrap()` obtains a new access token and
   `/users/me` rehydrates the user so I stay on `/`.
10. **Given** the codebase, **when** I run `npm run lint`, `npm run typecheck`
    and `npm run build`, **then** all succeed with no errors.

## 8. Test plan

> Under the 2-minute budget. No real backend network in unit/component tests —
> mock `fetch`/the API client (e.g. MSW or a fetch mock). The single Playwright
> e2e may run against a test backend or a mocked network; keep it fast.

- **Unit (Vitest):**
  - `api-client`: injects Bearer header; on `401` calls refresh once and replays;
    concurrent-401 dedupes to one refresh; refresh-failure clears auth; parses
    `422` field errors and generic `detail` into `ApiError`.
  - `token-store`: set/clear access token; access token never written to
    `localStorage`; refresh persistence behaves as designed.
  - Form validation helpers (email, password rules, password match).
- **Component (Vitest + React Testing Library):**
  - Login form: renders shadcn fields; shows error `Alert` on `401`; disables
    submit + shows spinner while pending.
  - Register form: blocks on mismatched passwords/invalid email; shows backend
    field errors on `422`; duplicate `409` shows an `Alert`.
  - `<RequireAuth>`: redirects when unauthenticated; renders children when authed.
- **E2E (Playwright):** one happy-path flow — visit `/`, get redirected to
  `/login`, register a new account, log in, see `Welcome, ...` on `/`, log out,
  get redirected back to `/login`. (Run against the real test backend if cheap;
  otherwise mock network responses.)
- **Performance/budget note:** mocked network in unit/component tests; the lone
  e2e flow is short; no LLM, no compile, no real WS.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] ESLint + Prettier clean; `tsc --noEmit` clean; `npm run build` succeeds.
- [ ] `VITE_API_BASE_URL` (and any `CORS_ORIGINS` change) documented in
      `.env.example`; token-storage/refresh ADR added under `docs/`.
- [ ] All form controls use shadcn/ui components (no hand-rolled CSS controls).
- [ ] No Overleaf code copied; no CSRF/cookie-session model introduced.
