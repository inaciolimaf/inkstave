/**
 * Per-context authentication for the e2e suite (spec 54).
 *
 * Inkstave uses **rotating** refresh tokens with reuse-detection: presenting a
 * refresh token a second time revokes the whole family. So a single shared
 * storage-state cannot be reused across parallel browser contexts. Instead each
 * context gets its **own fresh** refresh token (its own family) via a quick API
 * login, injected into localStorage before the first navigation. The guard means
 * the app's own rotation (which rewrites localStorage) is never clobbered on
 * later navigations within the same test.
 */
import type { BrowserContext } from "@playwright/test";

import { ApiClient } from "./api";
import { REFRESH_TOKEN_KEY } from "./env";

export async function injectAuth(context: BrowserContext, email: string): Promise<void> {
  const client = new ApiClient();
  const pair = await client.login(email);
  await context.addInitScript(
    ([key, token]) => {
      try {
        if (!window.localStorage.getItem(key)) window.localStorage.setItem(key, token);
      } catch {
        // ignore storage failures
      }
    },
    [REFRESH_TOKEN_KEY, pair.refresh_token] as const,
  );
}
