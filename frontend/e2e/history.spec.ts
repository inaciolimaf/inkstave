/**
 * Journey 6 — Version history (spec 54 §5.3). Edits to a document are captured as
 * snapshots; the history timeline lists versions, a diff is viewable, and
 * restoring an earlier version changes the editor content back.
 */
import { test, expect } from "./support/fixtures";
import { EditorPage, HistoryPanel } from "./support/pages";

test("edit → versions appear → view a diff → restore reverts the editor @smoke", async ({
  page,
  apiA,
  seedProject,
}) => {
  const { projectId, docId } = await seedProject();
  const editor = new EditorPage(page);
  const history = new HistoryPanel(page);

  await editor.open(projectId);
  await editor.openFile("main.tex");
  await expect(page.locator(".cm-content[contenteditable='true']")).toBeVisible({
    timeout: 20_000,
  });

  // Make two distinct edits; the CRDT stream is captured into history versions.
  await editor.type(" ALPHA-EDIT");
  await apiA.waitForVersions(projectId, docId, 1);
  await editor.type(" BETA-EDIT");
  await apiA.waitForVersions(projectId, docId, 2);
  await expect(editor.content()).toContainText("BETA-EDIT");

  // Open the timeline and pick the oldest version (predates BETA-EDIT).
  await history.open();
  const versions = page.getByRole("button", { name: /v\d+ · \d+ change/ });
  await expect(versions.first()).toBeVisible();
  await versions.last().click();

  // Its diff is viewable.
  await expect(page.getByRole("region", { name: "Version diff" })).toBeVisible();

  // Restore it → the editor content reverts (loses the later BETA-EDIT).
  await page.getByRole("button", { name: "Restore this version" }).click();
  await expect(page.getByText(/Restore version \d+\?/)).toBeVisible();
  await page.getByRole("button", { name: "Restore", exact: true }).click();
  await expect(page.getByText(/created version \d+/i)).toBeVisible();
  await expect(editor.content()).not.toContainText("BETA-EDIT");
});
