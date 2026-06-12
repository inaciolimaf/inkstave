/**
 * e2e environment configuration (spec 54).
 *
 * Everything that could differ between a developer machine and CI comes from
 * env vars with sane defaults — nothing is hard-coded to one machine. The
 * Playwright config, global setup and specs all read these.
 */

function num(name: string, fallback: number): number {
  const raw = process.env[name];
  const n = raw ? Number(raw) : NaN;
  return Number.isFinite(n) ? n : fallback;
}

export const e2e = {
  /** Where Playwright points the browser (the Vite preview origin). */
  baseUrl: process.env.E2E_BASE_URL ?? "http://localhost:4173",
  /** Backend API origin the frontend talks to. */
  apiUrl: process.env.E2E_API_URL ?? "http://localhost:8099",
  /** Port the backend Uvicorn listens on (used by the bring-up command). */
  backendPort: num("E2E_BACKEND_PORT", 8099),
  /** Port the Vite preview server listens on. */
  frontendPort: num("E2E_FRONTEND_PORT", 4173),
  /** Flake retries (CI defaults to 1, local to 0). */
  retries: num("E2E_RETRIES", process.env.CI ? 1 : 0),
  /**
   * Worker parallelism. When `E2E_PLAYWRIGHT_WORKERS` is set it is honoured
   * verbatim (explicit override). When unset this is `undefined`, and
   * playwright.config.ts deliberately applies a default of **2** — NOT
   * "from cores" as spec 54 §5.5 suggests. The whole suite shares ONE backend
   * and ONE ARQ worker, so cores-many browser contexts saturate them and flake
   * the collab/agent/compile journeys; 2 is the reliable engineering choice.
   * See the rationale comment on `workers:` in playwright.config.ts.
   */
  workers: process.env.E2E_PLAYWRIGHT_WORKERS ? num("E2E_PLAYWRIGHT_WORKERS", 1) : undefined,
};

/** A password that satisfies the backend's policy (letter + digit, not email-like). */
export const E2E_PASSWORD = "e2ePassw0rd";

/** localStorage key the frontend persists the refresh token under (token-store.ts). */
export const REFRESH_TOKEN_KEY = "inkstave.refresh_token";

/** Where global setup records the seeded users (so specs can read their ids/emails). */
export const RUN_CONTEXT_FILE = "e2e/.auth/run-context.json";

export interface SeededUser {
  email: string;
  displayName: string;
  id: string;
}

export interface RunContext {
  userA: SeededUser;
  userB: SeededUser;
}
