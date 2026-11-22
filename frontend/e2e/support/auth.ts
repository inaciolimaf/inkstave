/**
 * Per-context authentication for the e2e suite (spec 54).
 *
 * Inkstave uses **rotating** refresh tokens with reuse-detection: presenting a refresh
 * token a second time revokes the whole family. So a token cannot be shared by parallel
 * browser contexts. A test that uses the default `page` gets its token from the worker's
 * chain (see `session.ts`). A test that needs a context of its own calls `injectAuth`,
 * which logs in for a fresh token (its own family). Either way the token is written into
 * localStorage before the first navigation, and the app's own rotation is never clobbered:
 * the guard only writes into an empty store.
 */
import type { BrowserContext } from "@playwright/test";

import { ApiClient } from "./api";
import { REFRESH_TOKEN_KEY } from "./env";

/** Seed a context's localStorage with a refresh token before its first navigation. */
export async function seedRefreshToken(context: BrowserContext, refreshToken: string): Promise<void> {
  await context.addInitScript(
    ([key, token]) => {
      try {
        if (!window.localStorage.getItem(key)) window.localStorage.setItem(key, token);
      } catch {
        // ignore storage failures
      }
    },
    [REFRESH_TOKEN_KEY, refreshToken] as const,
  );
}

/** Log in as `email` for a context of its own (one password hash, its own token family). */
export async function injectAuth(context: BrowserContext, email: string): Promise<void> {
  const pair = await new ApiClient().login(email);
  await seedRefreshToken(context, pair.refresh_token);
}
