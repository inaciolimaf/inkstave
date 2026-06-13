import { defineConfig, devices } from "@playwright/test";

import { e2e } from "./e2e/support/env";

/**
 * End-to-end suite (spec 54) — real-stack smoke journeys against a test-profile
 * backend (Uvicorn + ARQ worker + Postgres/Redis) with deterministic stubs:
 * `COMPILE_MODE=mock` (canned PDF/log, no Tectonic) and `LLM_STUB=true`
 * (scripted agent, no network). See docs/e2e-strategy.md.
 *
 * Bring-up is Option A: Playwright `webServer` starts the backend (which resets
 * the DB + runs the worker) and the Vite preview of a prebuilt bundle; Postgres
 * and Redis come from `docker-compose.test.yml`. Two projects: `smoke` (default,
 * in-budget) and `full` (opt-in, `@full` — real Tectonic, edge cases).
 */

// Backend env, injected into the bring-up command (nothing hard-coded per machine).
const backendEnv: Record<string, string> = {
  DATABASE_URL:
    process.env.E2E_DATABASE_URL ??
    "postgresql+asyncpg://inkstave:inkstave@localhost:5433/inkstave_e2e",
  REDIS_URL: process.env.E2E_REDIS_URL ?? "redis://localhost:6380/0",
  JWT_SECRET: process.env.E2E_JWT_SECRET ?? "e2e-test-secret-0123456789abcdef0123456789",
  ENVIRONMENT: "test",
  LOG_JSON: "false",
  COMPILE_MODE: process.env.COMPILE_MODE ?? "mock",
  LLM_STUB: process.env.LLM_STUB ?? "true",
  COMPILE_WORKDIR_ROOT: process.env.E2E_COMPILE_WORKDIR ?? "/tmp/inkstave-e2e-compiles",
  // Flush captured history quickly so the history journey sees versions promptly.
  HISTORY_DEBOUNCE_MS: process.env.E2E_HISTORY_DEBOUNCE_MS ?? "200",
  COLLAB_TEXT_FLUSH_DEBOUNCE_MS: "200",
  CORS_ORIGINS: e2e.baseUrl,
  // Generous auth limits so global setup + auth journey never hit a 429.
  RATE_LIMIT_LOGIN: "1000/60",
  RATE_LIMIT_REGISTER: "1000/60",
  RATE_LIMIT_REFRESH: "1000/60",
  // Email link-based auth flows (spec 104): capture emails to a file (no SMTP),
  // generous limits, and build links against the preview origin.
  RATE_LIMIT_AUTH_PASSWORD: "1000/60",
  RATE_LIMIT_VERIFY_EMAIL: "1000/60",
  RATE_LIMIT_MAGIC_LINK: "1000/60",
  RATE_LIMIT_RESET_PASSWORD: "1000/60",
  EMAIL_BACKEND: "file",
  EMAIL_FILE_DIR: e2e.emailDir,
  FRONTEND_URL: e2e.baseUrl,
  E2E_BACKEND_PORT: String(e2e.backendPort),
};

// Frontend build env so the bundle talks to the e2e backend (collab WS derives from it).
const frontendBuildEnv = `VITE_API_BASE_URL=${e2e.apiUrl}`;

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: e2e.retries,
  // Cap parallelism by default: the whole suite shares ONE backend + ONE ARQ
  // worker, so too many concurrent browser contexts saturate them — slowing the
  // collab WS sync and async agent/compile jobs enough to flake (spec 55). Two
  // workers keeps the suite fast while staying reliable. Override with
  // E2E_PLAYWRIGHT_WORKERS.
  workers: e2e.workers ?? 2,
  reporter: process.env.CI ? "line" : "list",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: e2e.baseUrl,
    trace: "on-first-retry",
    video: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    // Auth is per-context via a fresh-login fixture (rotating refresh tokens make a
    // shared static storageState unusable across parallel contexts) — see support/auth.ts.
    {
      name: "smoke",
      grepInvert: /@full/,
      use: { ...devices["Desktop Chrome"] },
    },
    // The full tier (opt-in, `@full`) covers edge cases beyond the happy path AND
    // a second browser engine (spec 54 §8 item 4): it runs on Firefox so we catch
    // engine-specific regressions the Chromium smoke tier would miss. Kept out of
    // the default run by the `@full` grep, so the smoke budget is unaffected.
    {
      name: "full",
      grep: /@full/,
      use: { ...devices["Desktop Firefox"] },
    },
  ],
  webServer: [
    {
      command: "bash e2e/bringup-backend.sh",
      url: `${e2e.apiUrl}/readyz`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: backendEnv,
    },
    {
      command: `bash -c "${frontendBuildEnv} pnpm build && pnpm exec vite preview --host 127.0.0.1 --port ${e2e.frontendPort} --strictPort"`,
      url: e2e.baseUrl,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
