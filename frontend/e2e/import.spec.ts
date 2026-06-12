/**
 * Journey — Project import from a .zip (spec 101). Authenticated as User A: open
 * the dashboard, import a tiny fixture archive (one main.tex + one tiny PNG), and
 * confirm the real ARQ worker reconstructs it and the new project opens.
 *
 * The fixture is a few hundred bytes (stored, no compression); the import job runs
 * for real on the shared worker — no large archive, so it stays fast.
 */
import { test, expect } from "./support/fixtures";
import { DashboardPage } from "./support/pages";
import { makeStoredZip } from "./support/zip";

test("import a .zip → worker reconstructs → new project opens @smoke", async ({ page }) => {
  const dashboard = new DashboardPage(page);
  await dashboard.goto();

  const zip = makeStoredZip({
    "main.tex": "\\documentclass{article}\n\\begin{document}Imported\\end{document}\n",
    "figures/logo.png": Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 1, 2, 3]),
  });

  await page.getByRole("button", { name: "Import (.zip)" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Import a project" })).toBeVisible();

  await dialog.getByLabel("Project name (optional)").fill("Imported via e2e");
  await dialog.locator('input[type="file"]').setInputFiles({
    name: "paper.zip",
    mimeType: "application/zip",
    buffer: zip,
  });
  await dialog.getByRole("button", { name: "Import" }).click();

  // Upload + worker reconstruction, then the dialog navigates to the new project.
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]+$/i, { timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Share" })).toBeVisible();

  // The imported project is listed back on the dashboard.
  await dashboard.goto();
  await expect(dashboard.projectLink("Imported via e2e")).toBeVisible();
});
