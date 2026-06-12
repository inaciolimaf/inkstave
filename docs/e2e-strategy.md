# E2E strategy (spec 54)

Inkstave's end-to-end suite is a **Playwright** project at `frontend/e2e/`. It
drives the real frontend bundle against a real **test-profile backend** (Uvicorn
+ ARQ worker + Postgres + Redis) with two deterministic stubs so it stays fast
and reproducible. It is the integration-confidence capstone of the hardening
phase and runs as the **smoke tier** inside the global 2-minute budget (spec 53).

## Bring-up (Option A: Playwright `webServer`)

`frontend/playwright.config.ts` starts everything and tears it down:

1. **Infra** — Postgres + Redis come from `docker-compose.test.yml` on dedicated
   ports (5433 / 6380, `tmpfs`) so a run never collides with the dev stack. Start
   it once: `docker compose -f docker-compose.test.yml up -d`.
2. **Backend** — `e2e/bringup-backend.sh` resets the test DB to a clean migrated
   state (`backend/scripts/e2e_reset_db.py`), then runs the ARQ worker + Uvicorn
   together (a trap tears the worker down with the server). Playwright waits on
   `/readyz`. All config (DSNs, `COMPILE_MODE=mock`, `LLM_STUB=true`, CORS, …) is
   injected as env from the config — nothing is hard-coded to a machine.
3. **Frontend** — `vite build` (with `VITE_API_BASE_URL` pointing at the e2e
   backend) then `vite preview`. Playwright waits on the preview origin.
4. **Global setup** (`e2e/global-setup.ts`) registers the two e2e users via the
   API and writes `e2e/.auth/run-context.json` (git-ignored).

Run the suite: `pnpm exec playwright test` (from `frontend/`). The default
project is `smoke`; `full` is opt-in.

## Auth: per-context fresh login (not a shared storage-state)

Inkstave uses **rotating** refresh tokens with reuse-detection (presenting a
token twice revokes the family). A single shared `storageState` therefore cannot
be reused across parallel contexts. Instead each browser context gets its **own
fresh** refresh token via a quick API login, injected into `localStorage` before
the first navigation (`e2e/support/auth.ts`); the app exchanges it for a session
on load. The auth journey is the exception — it starts unauthenticated and drives
register/login through the UI.

## Stubs (deterministic, env-selected, production untouched)

Both live in `backend/src/inkstave/testkit/` and are activated **only** by env
flags; the default production paths never import them.

- **`COMPILE_MODE=mock`** → `MockTectonicRunner` writes a tiny, valid one-page PDF
  (built in-process, correct xref) plus a canned log into the compile output dir —
  no Tectonic subprocess. A document containing the sentinel
  `\inkstaveforceerror` (or `% INKSTAVE_E2E_COMPILE_ERROR`) yields a realistic
  LaTeX error log so the compile journey can assert log + problem annotations.
- **`LLM_STUB=true`** → `StubAgentLLM` drives the agent graph through a fixed
  `search_project → read_file → propose_edit` tool sequence and a fixed reply,
  producing a deterministic per-file diff against the seeded document — no network.

The ARQ worker (`compile/worker.py`) selects these at startup based on the flags.

## Smoke vs full

| Journey (spec 54 §5.3)        | Smoke (default, in budget)                          | Full (`@full`, opt-in/nightly)                 |
| ----------------------------- | --------------------------------------------------- | ---------------------------------------------- |
| 1. Auth                       | register → login → logout → login (UI)              | —                                              |
| 2. Project lifecycle          | create → rename → reload-persist → delete           | —                                              |
| 3. Files & editing            | create `.tex` → edit → reload persists              | —                                              |
| 4. Compile & preview          | mock compile → PDF renders + log; injected error → annotations | **real Tectonic** 1-page compile     |
| 5. Share & live collaboration | invite editor → two contexts edit live both ways; viewer read-only | viewer/permission edge cases    |
| 6. Version history            | edit → versions → diff → restore reverts editor     | —                                              |
| 7. AI agent diff              | stub proposes diff → review → apply; nothing applied before confirm | multi-hunk partial accept/reject |
| Harness sanity                | stub PDF/log + stub agent diff (API-only)           | —                                              |

Run full: `pnpm exec playwright test --project=full`. The `full` project is
**excluded from the default run** (and the budget) — it is invoked explicitly and
may add a second browser engine, real Tectonic, and partial-accept paths.

Config: one Chromium engine in smoke, parallel workers, prebuilt bundle, mocked
compile, deterministic stub LLM, traces/video/screenshots **on failure only**,
retries `1` in CI / `0` locally. No fixed `waitForTimeout` for readiness — specs
wait on selectors/network; the LLM and compile are stubbed precisely.

## Known limitation

Fine-grained **presence rendering** (remote cursor caret + "online now" avatars)
is asserted by the spec-32 Vitest unit suite (`OnlineUsers` / `usePresence` /
`presence-convergence`), not in e2e: against the real awareness channel a peer's
awareness frames did not reliably reach a late-joining context within the test
window even though document sync (the headline real-time assertion) propagated
both ways. The collab smoke spec therefore asserts live two-way editing + viewer
read-only; the awareness-propagation timing is flagged for the spec-55 refactor.

The backend fast suite also shows a pre-existing teardown flake
(`test_collab_manager` — asyncpg "connection is closed") only under very high
`-n auto` worker counts; it is green serially and at `-n 4`, and is likewise a
spec-55 candidate.
