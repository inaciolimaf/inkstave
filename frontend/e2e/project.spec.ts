/**
 * Journey 2 — Project lifecycle (spec 54 §5.3). Authenticated as User A: create a
 * project from the dashboard, see it listed, rename it, confirm it persists across
 * a reload, then delete it and confirm it disappears.
 */
import { uniqueId } from "./support/api";
import { test, expect } from "./support/fixtures";
import { DashboardPage } from "./support/pages";

test("create → rename → persist across reload → delete @smoke", async ({ page }) => {
  const name = `Proj ${uniqueId("p")}`;
  const renamed = `${name} (renamed)`;
  const dashboard = new DashboardPage(page);

  await dashboard.goto();
  await dashboard.createProject(name);
  await expect(dashboard.projectLink(name)).toBeVisible();

  await dashboard.rename(name, renamed);
  await expect(dashboard.projectLink(renamed)).toBeVisible();

  // Persists across a full reload.
  await page.reload();
  await expect(dashboard.projectLink(renamed)).toBeVisible();

  // Open it from the dashboard → the URL becomes /projects/:id and the editor
  // shell renders (spec 16 §8 / AC §10) → go back to the list (no real compile).
  await dashboard.open(renamed);
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]+$/i);
  await expect(page.getByRole("button", { name: "Share" })).toBeVisible();
  await page.goBack();
  await expect(dashboard.heading()).toBeVisible();
  await expect(dashboard.projectLink(renamed)).toBeVisible();

  // Delete (with confirm) → gone from the list.
  await dashboard.delete(renamed);
  await expect(dashboard.projectLink(renamed)).toHaveCount(0);
});
