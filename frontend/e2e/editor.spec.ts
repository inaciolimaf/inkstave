/**
 * Journey 3 — Files & editing (spec 54 §5.3). Open a project, create a new
 * `.tex` file in the tree, open it, type LaTeX, and confirm it persists across a
 * reload. The editor runs in live-CRDT mode (collab enabled), so persistence is
 * asserted by reload rather than a REST "Saved" badge.
 */
import { ApiClient } from "./support/api";
import { injectAuth } from "./support/auth";
import { test, expect } from "./support/fixtures";
import { EditorPage } from "./support/pages";

test("create a .tex file, edit it, and the content survives a reload @smoke", async ({
  page,
  seedProject,
}) => {
  const { projectId } = await seedProject();
  const editor = new EditorPage(page);
  await editor.open(projectId);

  // Create a new file via the tree; it appears in the tree.
  await editor.createFile("chapter.tex");
  await expect(page.getByText("chapter.tex", { exact: true })).toBeVisible();

  // Open it and wait for the live editor to become editable, then type.
  await editor.openFile("chapter.tex");
  await editor.waitEditable();
  await editor.type("\\section{Methods}");
  await expect(editor.content()).toContainText("\\section{Methods}");

  // Reload → reopen the file → the edit persisted (CRDT state durable server-side).
  await page.reload();
  await editor.openFile("chapter.tex");
  await expect(editor.content()).toContainText("\\section{Methods}");
});

/**
 * Spec 18 §8 — read-only viewing + in-editor font size. A viewer opens a seeded
 * document: line numbers and syntax highlighting render, typing does NOT change
 * the content (read-only), and increasing the font size in the in-editor settings
 * popover changes the editor's computed font-size.
 */
test("read-only viewer sees highlighting + line numbers and can resize the font @smoke", async ({
  browser,
  apiA,
  runContext,
  seedProject,
}) => {
  const { projectId } = await seedProject();
  // Share the project with User B as a VIEWER so the editor mounts read-only.
  const viewer = new ApiClient();
  await viewer.login(runContext.userB.email);
  const invite = await apiA.invite(projectId, runContext.userB.email, "viewer");
  await viewer.acceptInvite(invite.token);

  const ctx = await browser.newContext();
  await injectAuth(ctx, runContext.userB.email);
  const page = await ctx.newPage();
  const editor = new EditorPage(page);
  await editor.open(projectId);
  await editor.openFile("main.tex");

  // The viewer's editor mounts read-only: content is not contenteditable.
  const readOnlyContent = page.locator(".cm-content[contenteditable='false']");
  await expect(readOnlyContent).toBeVisible({ timeout: 20_000 });
  await expect(editor.content()).toContainText("\\section{Introduction}");

  // Line numbers (lineNumbers gutter) and syntax-highlight token spans both render.
  expect(await editor.lineNumbers().count()).toBeGreaterThan(0);
  expect(await editor.tokenSpans().count()).toBeGreaterThan(0);

  // Typing into a read-only editor does not change its content.
  const before = await editor.content().innerText();
  await editor.content().click();
  await page.keyboard.type("SHOULD-NOT-APPEAR");
  await expect(editor.content()).not.toContainText("SHOULD-NOT-APPEAR");
  expect(await editor.content().innerText()).toBe(before);

  // Increase the font size via the in-editor settings popover → computed font-size grows.
  const fontBefore = await editor
    .editorRoot()
    .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  await editor.openSettings();
  await editor.setFontSize(24);
  await expect
    .poll(() => editor.editorRoot().evaluate((el) => parseFloat(getComputedStyle(el).fontSize)))
    .toBe(24);
  expect(24).toBeGreaterThan(fontBefore);

  await ctx.close();
});

/**
 * Spec 19 §8 — REST autosave: edit a seeded doc, see "Saving…" then "Saved", reload,
 * and the edit persisted. The REST save-status badge (`SaveStatusIndicator`) only
 * mounts when live collaboration is OFF for the document; the e2e bundle is built
 * with collab enabled (so docs use the CRDT editor and persist by reload, covered
 * above). This test exercises the REST autosave path when it is available, so it
 * stays meaningful in a collab-disabled build and is skipped otherwise.
 */
test("REST autosave shows Saving… then Saved and the edit survives a reload @smoke", async ({
  page,
  seedProject,
}) => {
  const { projectId } = await seedProject();
  const editor = new EditorPage(page);
  await editor.open(projectId);
  await editor.openFile("main.tex");

  // The REST save-status region only renders in non-collab/REST mode.
  const restMode = await editor
    .saveStatus()
    .isVisible()
    .catch(() => false);
  test.skip(
    !restMode,
    "REST autosave badge is only mounted when live collaboration is disabled (the e2e bundle builds with collab enabled).",
  );

  // Edit → the autosave badge transitions Saving… → Saved. The "clean" badge can
  // read "Saved" or a relative "Saved Xs ago", so assert on the save-status region.
  await editor.type("\\section{REST Autosave}");
  await expect(editor.savingBadge()).toBeVisible({ timeout: 10_000 });
  await expect(editor.saveStatus()).toContainText(/Saved/, { timeout: 15_000 });

  // Reload → reopen → the REST-saved edit persisted.
  await page.reload();
  await editor.openFile("main.tex");
  await expect(editor.content()).toContainText("\\section{REST Autosave}");
});
