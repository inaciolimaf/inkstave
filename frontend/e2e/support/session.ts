/**
 * Worker-scoped sign-in for the e2e suite (spec 54).
 *
 * Refresh tokens rotate, and presenting a rotated one again revokes its whole family
 * (backend auth), so a single token cannot serve several browser contexts. A Playwright
 * worker runs its tests one at a time, so each worker keeps one chain of tokens per user:
 *
 * 1. `begin` rotates the chain once and hands the test its own fresh pair;
 * 2. the browser rotates that token again during the test;
 * 3. `keep` takes the newest token back from the browser, so the next test starts from it.
 *
 * When the chain breaks (no read-back, or the family was revoked) `begin` logs in again: one
 * password hash instead of one per test. Production rotation is not touched.
 */
import type { Page } from "@playwright/test";

import { ApiClient, type TokenPair } from "./api";
import { e2e, REFRESH_TOKEN_KEY } from "./env";

export interface SignedIn {
  email: string;
  accessToken: string;
  refreshToken: string;
}

/** Rotate a refresh token; null when the server refuses it (expired, revoked or reused). */
async function rotate(refreshToken: string): Promise<TokenPair | null> {
  const res = await fetch(`${e2e.apiUrl}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  return res.ok ? ((await res.json()) as TokenPair) : null;
}

/** The refresh chains of one Playwright worker, one per user. */
export class WorkerSessions {
  private readonly newest = new Map<string, string>();

  /** A signed-in pair for `email`, rotated from this worker's chain (a login the first time). */
  async begin(email: string): Promise<SignedIn> {
    const held = this.newest.get(email);
    const pair = (held ? await rotate(held) : null) ?? (await new ApiClient().login(email));
    this.newest.set(email, pair.refresh_token);
    return { email, accessToken: pair.access_token, refreshToken: pair.refresh_token };
  }

  /** Keep the token the browser holds after a test; null (the page is gone) keeps the chain as it is. */
  keep(email: string, refreshToken: string | null): void {
    if (refreshToken) this.newest.set(email, refreshToken);
  }
}

/** The refresh token the page's app holds in localStorage, or null when it cannot be read. */
export async function readRefreshToken(page: Page): Promise<string | null> {
  try {
    return await page.evaluate((key) => window.localStorage.getItem(key), REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}
