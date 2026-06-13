/**
 * Playwright global setup (spec 54 §5.2).
 *
 * Waits for the backend to be ready, registers the two e2e users (User A + User B)
 * via the API, and records a small run-context file the specs read for each user's
 * email/id. Browser auth itself is per-context (a fresh login per test, because
 * refresh tokens rotate — see support/auth.ts), so no shared storage-state is
 * written here. The auth journey registers its own throwaway user through the UI.
 */
import { mkdir, writeFile } from "node:fs/promises";

import { ApiClient, registerUser, uniqueId } from "./support/api";
import { e2e, RUN_CONTEXT_FILE, type RunContext } from "./support/env";

async function waitForBackend(timeoutMs = 60_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastErr: unknown;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${e2e.apiUrl}/readyz`);
      if (res.ok) return;
    } catch (err) {
      lastErr = err;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`backend not ready at ${e2e.apiUrl}/readyz: ${String(lastErr)}`);
}

export default async function globalSetup(): Promise<void> {
  await waitForBackend();
  await mkdir("e2e/.auth", { recursive: true });

  // Take the app past first-run setup: create the first admin so `needs_setup`
  // is false and unauthenticated users are redirected to /login (not /setup).
  // This is a dedicated admin account; the journey users (A/B) below stay regular
  // collaborators so per-role specs keep their semantics.
  await new ApiClient().bootstrapAdmin(`${uniqueId("admin")}@example.com`, "E2E Admin");

  const emailA = `${uniqueId("alice")}@example.com`;
  const emailB = `${uniqueId("bob")}@example.com`;

  const a = await registerUser(emailA, "Alice Adams");
  const b = await registerUser(emailB, "Bob Brown");

  const ctx: RunContext = {
    userA: { email: emailA, displayName: "Alice Adams", id: a.id },
    userB: { email: emailB, displayName: "Bob Brown", id: b.id },
  };
  await writeFile(RUN_CONTEXT_FILE, JSON.stringify(ctx, null, 2));
}
