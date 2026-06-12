/**
 * Journey — Project export to .zip (spec 102). Authenticated as User A: seed a
 * tiny project, open its dashboard actions menu, click "Download as .zip", and
 * assert a real browser download of a non-empty application/zip occurs.
 */
import { readFile } from "node:fs/promises";

import { uniqueId } from "./support/api";
import { test, expect } from "./support/fixtures";
import { DashboardPage } from "./support/pages";

test("download a project as .zip from the dashboard @smoke", async ({ page, seedProject }) => {
  const name = `Export ${uniqueId("e")}`;
  await seedProject(name);

  const dashboard = new DashboardPage(page);
  await dashboard.goto();
  await expect(dashboard.projectLink(name)).toBeVisible();

  await dashboard.row(name).getByRole("button", { name: "Project actions" }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("menuitem", { name: "Download as .zip" }).click();

  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.zip$/);

  const path = await download.path();
  expect(path).toBeTruthy();
  const bytes = await readFile(path!);
  // A valid (non-empty) zip starts with the local-file-header / EOCD "PK" magic.
  expect(bytes.length).toBeGreaterThan(0);
  expect(bytes.subarray(0, 2).toString("latin1")).toBe("PK");
});
