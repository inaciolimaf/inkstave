/**
 * Presence & awareness (spec 32 §8 / DoD §9). Exactly one Playwright two-context
 * test: two users open the same document; when user A moves the cursor / makes a
 * selection, user B sees a labelled remote cursor caret and a remote avatar for A.
 *
 * `collab.spec.ts` deliberately skips fine-grained presence rendering and defers
 * it to the Vitest unit suite; this is the one e2e that proves the rendering path
 * end-to-end over the real awareness WebSocket. Two browser contexts, each with
 * its own auth, both opening the same shared project.
 */
import type { BrowserContext, Page } from "@playwright/test";

import { injectAuth } from "./support/auth";
import { test, expect } from "./support/fixtures";
import { EditorPage } from "./support/pages";

async function openDoc(context: BrowserContext, email: string, projectId: string): Promise<Page> {
  await injectAuth(context, email);
  const page = await context.newPage();
  const editor = new EditorPage(page);
  await editor.open(projectId);
  await editor.openFile("main.tex");
  return page;
}

test("a moved cursor renders a labelled remote cursor + avatar in the other context @smoke", async ({
  browser,
  apiA,
  apiB,
  runContext,
  seedProject,
}) => {
  const { projectId } = await seedProject();
  // User A shares with User B as editor so both can join the same document.
  const invite = await apiA.invite(projectId, runContext.userB.email, "editor");
  await apiB.acceptInvite(invite.token);

  const ctxA = await browser.newContext();
  const ctxB = await browser.newContext();
  const pageA = await openDoc(ctxA, runContext.userA.email, projectId);
  const pageB = await openDoc(ctxB, runContext.userB.email, projectId);

  const editorA = new EditorPage(pageA);
  const editorB = new EditorPage(pageB);

  // Both editors finish syncing and become editable.
  await editorA.waitEditable();
  await editorB.waitEditable();

  // B sees A's avatar in the "online now" presence list (awareness propagated).
  await expect(editorB.presenceOf(runContext.userA.displayName)).toBeVisible({ timeout: 20_000 });

  // A moves the cursor and makes a selection (click into the doc, then select a word).
  await pageA.locator(".cm-content").click();
  await pageA.keyboard.press("Home");
  await pageA.keyboard.down("Shift");
  await pageA.keyboard.press("ArrowRight");
  await pageA.keyboard.press("ArrowRight");
  await pageA.keyboard.press("ArrowRight");
  await pageA.keyboard.up("Shift");

  // B renders A's remote cursor caret (y-codemirror.next) ...
  const caret = pageB.locator(".cm-ySelectionCaret").first();
  await expect(caret).toBeVisible({ timeout: 20_000 });

  // ... carrying a label with A's name (revealed on hover via .cm-ySelectionInfo).
  await caret.hover();
  await expect(caret.locator(".cm-ySelectionInfo")).toContainText(runContext.userA.displayName, {
    timeout: 10_000,
  });

  await ctxA.close();
  await ctxB.close();
});
