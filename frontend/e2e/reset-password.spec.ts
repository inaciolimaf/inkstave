/**
 * Journey — Password reset round trip (spec 104). Real-stack, no real email:
 * the backend's `file` email sender writes each message to disk (EMAIL_FILE_DIR),
 * and this spec reads the reset link from there — never a live inbox/SMTP.
 *
 * Seed a user → request a reset through the UI → read the link from the captured
 * email → set a new password → sign in with it. Starts from a clean browser (no
 * auto-auth fixture) because it drives the public auth pages itself.
 */
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { ApiClient, uniqueId } from "./support/api";
import { e2e, E2E_PASSWORD } from "./support/env";
import { DashboardPage, LoginPage } from "./support/pages";

/** Poll the captured-email dir for the most recent reset link sent to `email`. */
async function readResetToken(email: string): Promise<string> {
  let token: string | null = null;
  await expect
    .poll(
      async () => {
        let files: string[];
        try {
          files = await readdir(e2e.emailDir);
        } catch {
          return false; // dir not created yet
        }
        for (const name of files) {
          if (!name.endsWith(".json")) continue;
          const raw = await readFile(join(e2e.emailDir, name), "utf8");
          const mail = JSON.parse(raw) as { to: string; text_body: string };
          if (mail.to !== email) continue;
          const match = mail.text_body.match(/\/reset-password\?token=([^\s"<]+)/);
          if (match) {
            token = match[1];
            return true;
          }
        }
        return false;
      },
      { timeout: 15_000, intervals: [250, 500, 1000] },
    )
    .toBe(true);
  if (!token) throw new Error("reset token not found");
  return token;
}

test("request a reset, set a new password from the link, then sign in @smoke", async ({ page }) => {
  const email = `${uniqueId("reset")}@example.com`;
  const newPassword = "Resetpass1";
  const login = new LoginPage(page);
  const dashboard = new DashboardPage(page);

  // Seed the account via the API (the journey is about reset, not registration).
  await new ApiClient().register(email, "Reset User", E2E_PASSWORD);

  // Request the reset link through the public UI page.
  await page.goto("/forgot-password");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: /send reset link/i }).click();
  await expect(page.getByText(/a reset link is on its way/i)).toBeVisible();

  // Read the link the backend "sent" (from the file sender, no real inbox).
  const token = await readResetToken(email);

  // Set a new password from the link.
  await page.goto(`/reset-password?token=${token}`);
  await page.getByLabel("New password").fill(newPassword);
  await page.getByLabel("Confirm new password").fill(newPassword);
  await page.getByRole("button", { name: /update password/i }).click();
  await expect(page.getByText(/password updated/i)).toBeVisible();

  // Tokens were revoked, so the page directs to /login — sign in with the new one.
  await expect(page).toHaveURL(/\/login$/);
  await login.login(email, newPassword);
  await expect(page).toHaveURL(/\/projects$/);
  await expect(dashboard.heading()).toBeVisible();
});
