/**
 * Journey — Account settings (spec 59). On the default User-A session: edit the
 * profile, change editor preferences and see the editor reflect them, start an
 * email change (pending state), and gate the delete dialog. A throwaway user
 * exercises the destructive password change + re-login so User A stays usable.
 */
import { ApiClient, uniqueId } from "./support/api";
import { injectAuth } from "./support/auth";
import { E2E_PASSWORD } from "./support/env";
import { test, expect } from "./support/fixtures";
import { EditorPage } from "./support/pages";

test("profile, editor prefs, email-change and delete gating @smoke", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

  // Profile: rename and persist across a reload.
  const newName = `Renamed ${uniqueId("n")}`;
  await page.getByLabel("Display name").fill(newName);
  await page.getByRole("button", { name: "Save profile" }).click();
  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue(newName);

  // Editor preferences: set a distinctive font size + dark theme.
  await page.getByLabel("Font size").click();
  await page.getByRole("option", { name: "28px" }).click();
  await page.getByLabel("Theme").click();
  await page.getByRole("option", { name: "Dark" }).click();

  // Email change: shows the "confirmation sent" state, active email unchanged.
  await page.getByLabel("New email").fill(`changed-${uniqueId("e")}@example.com`);
  await page.getByLabel("Password", { exact: true }).fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Change email" }).click();
  await expect(page.getByText(/confirmation link/i)).toBeVisible();

  // Delete dialog: requires the password AND a typed confirmation.
  await page.getByRole("button", { name: "Delete my account" }).click();
  const confirm = page.getByRole("button", { name: "Delete account" });
  await expect(confirm).toBeDisabled();
  await page.getByLabel("Password", { exact: true }).fill(E2E_PASSWORD);
  await page.getByLabel("Type DELETE").fill("DELETE");
  await expect(confirm).toBeEnabled();
  await page.getByRole("button", { name: "Cancel" }).click(); // never actually delete User A
});

test("editor reflects the chosen font size @smoke", async ({ page, seedProject }) => {
  const { projectId, docName } = await seedProject("Prefs");

  await page.goto("/settings");
  await page.getByLabel("Font size").click();
  await page.getByRole("option", { name: "28px" }).click();

  const editor = new EditorPage(page);
  await editor.open(projectId);
  await editor.openFile(docName);
  await editor.waitEditable();
  const fontSize = await page
    .locator(".cm-content")
    .evaluate((el) => getComputedStyle(el).fontSize);
  expect(fontSize).toBe("28px");
});

test("change password then re-login with the new one @smoke", async ({ browser }) => {
  // A throwaway account so we never break the shared User A.
  const email = `pw-${uniqueId("u")}@example.com`;
  const api = new ApiClient();
  await api.register(email, "Throwaway"); // password defaults to E2E_PASSWORD

  const context = await browser.newContext();
  await injectAuth(context, email);
  const page = await context.newPage();
  await page.goto("/settings");

  const newPassword = "Rotated9Pass";
  await page.getByLabel("Current password").fill(E2E_PASSWORD);
  await page.getByLabel("New password", { exact: true }).fill(newPassword);
  await page.getByLabel("Confirm new password").fill(newPassword);
  await page.getByRole("button", { name: "Change password" }).click();

  // The change signs out and routes to login.
  await expect(page).toHaveURL(/\/login$/);
  await context.close();

  // The new password works; the old one no longer does.
  await expect(new ApiClient().login(email, newPassword)).resolves.toBeTruthy();
  await expect(new ApiClient().login(email, E2E_PASSWORD)).rejects.toThrow();
});
