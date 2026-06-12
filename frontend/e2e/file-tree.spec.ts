/**
 * File-tree flow (spec 17 §8). Exactly one Playwright spec covering the full
 * file-tree journey against the seeded project:
 *   create folder → create a doc inside it → rename the doc → move it to root →
 *   upload a small binary file → delete the folder.
 * The tree state is asserted after each step.
 *
 * Notes:
 *  - The tree uses native HTML5 drag-and-drop, which Playwright's synthetic
 *    pointer events drive unreliably (the browser's DnD threshold + dataTransfer
 *    are not simulated). The "Move to root" row action invokes the *same*
 *    `doMove(node, root)` code path a drop-on-root triggers, so we exercise the
 *    move-to-root behaviour through it for a stable assertion.
 *  - The upload uses a tiny in-memory binary via `setInputFiles` so it stays fast.
 */
import { test, expect } from "./support/fixtures";
import { EditorPage } from "./support/pages";

test("create folder, add+rename a doc, move it to root, upload a binary, delete the folder @smoke", async ({
  page,
  seedProject,
}) => {
  const { projectId } = await seedProject();
  const editor = new EditorPage(page);
  await editor.open(projectId);

  const tree = page.getByRole("tree", { name: "Project files" });
  await expect(tree).toBeVisible();

  // 1) Create a folder.
  await page.getByRole("button", { name: "New folder" }).click();
  const newFolderDialog = page.getByRole("dialog");
  await newFolderDialog.getByLabel("Name").fill("chapters");
  await newFolderDialog.getByRole("button", { name: "Create" }).click();
  await expect(tree.getByText("chapters", { exact: true })).toBeVisible();

  // 2) Create a doc *inside* that folder (select the folder first so it's the parent).
  await tree.getByText("chapters", { exact: true }).click();
  await page.getByRole("button", { name: "New file" }).first().click();
  const newFileDialog = page.getByRole("dialog");
  await newFileDialog.getByLabel("Name").fill("intro.tex");
  await newFileDialog.getByRole("button", { name: "Create" }).click();
  await expect(tree.getByText("intro.tex", { exact: true })).toBeVisible();

  // 3) Rename the doc via its row actions menu → inline input → Enter.
  await tree.getByRole("button", { name: "Actions for intro.tex" }).click();
  await page.getByRole("menuitem", { name: "Rename" }).click();
  const renameInput = page.getByLabel("New name");
  await renameInput.fill("chapter1.tex");
  await renameInput.press("Enter");
  await expect(tree.getByText("chapter1.tex", { exact: true })).toBeVisible();
  await expect(tree.getByText("intro.tex", { exact: true })).toHaveCount(0);

  // 4) Move the doc to the root (same code path as drag-to-root; see file header).
  await tree.getByRole("button", { name: "Actions for chapter1.tex" }).click();
  await page.getByRole("menuitem", { name: "Move to root" }).click();
  // It now sits at the root: its row is no longer nested under the "chapters" group.
  const movedRow = tree.getByRole("treeitem").filter({ hasText: "chapter1.tex" });
  await expect(movedRow).toHaveAttribute("aria-level", "1");

  // 5) Upload a small binary file via the hidden file input.
  const pngBytes = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x01]);
  await page.locator('input[type="file"]').setInputFiles({
    name: "logo.png",
    mimeType: "image/png",
    buffer: pngBytes,
  });
  await expect(page.getByText("Done", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(tree.getByText("logo.png", { exact: true })).toBeVisible();

  // 6) Delete the (now-empty) folder and confirm.
  await tree.getByRole("button", { name: "Actions for chapters" }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  const confirm = page.getByRole("alertdialog");
  await expect(confirm).toContainText("chapters");
  await confirm.getByRole("button", { name: "Delete" }).click();
  await expect(tree.getByText("chapters", { exact: true })).toHaveCount(0);

  // The moved doc and uploaded file remain at the root.
  await expect(tree.getByText("chapter1.tex", { exact: true })).toBeVisible();
  await expect(tree.getByText("logo.png", { exact: true })).toBeVisible();
});
