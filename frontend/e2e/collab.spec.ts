/**
 * Journey 5 — Share & live collaboration (spec 54 §5.3). The headline real-time
 * test: User A shares a project with User B (invite by email), User B opens it,
 * both see each other's presence, an edit in one appears live in the other (both
 * ways), and a viewer cannot edit (read-only enforced).
 *
 * Two browser contexts, each with its own auth (storage state), both opening the
 * same shared project against the real collab WebSocket.
 */
import type { BrowserContext, Page } from "@playwright/test";

import { ApiClient } from "./support/api";
import { injectAuth } from "./support/auth";
import { test, expect } from "./support/fixtures";
import { EditorPage, ShareDialog } from "./support/pages";

async function openDoc(context: BrowserContext, email: string, projectId: string): Promise<Page> {
  await injectAuth(context, email);
  const page = await context.newPage();
  const editor = new EditorPage(page);
  await editor.open(projectId);
  await editor.openFile("main.tex");
  return page;
}

test("editor collaborator: live edits propagate both ways @smoke", async ({
  browser,
  apiA,
  apiB,
  runContext,
  seedProject,
}) => {
  const { projectId } = await seedProject();
  // User A shares with User B as editor (invite by email); User B accepts.
  const invite = await apiA.invite(projectId, runContext.userB.email, "editor");
  await apiB.acceptInvite(invite.token);

  const ctxA = await browser.newContext();
  const ctxB = await browser.newContext();
  const pageA = await openDoc(ctxA, runContext.userA.email, projectId);
  const pageB = await openDoc(ctxB, runContext.userB.email, projectId);

  // Both editors become editable once synced.
  await expect(pageA.locator(".cm-content[contenteditable='true']")).toBeVisible({
    timeout: 20_000,
  });
  await expect(pageB.locator(".cm-content[contenteditable='true']")).toBeVisible({
    timeout: 20_000,
  });

  // A types → B sees it live.
  await pageA.locator(".cm-content").click();
  await pageA.keyboard.type("EDIT-FROM-A");
  await expect(pageB.locator(".cm-content")).toContainText("EDIT-FROM-A", { timeout: 15_000 });

  // B types → A sees it live (both directions). Two independent contexts editing the
  // same shared document and converging live is the headline real-time assertion.
  await pageB.locator(".cm-content").click();
  await pageB.keyboard.type("EDIT-FROM-B");
  await expect(pageA.locator(".cm-content")).toContainText("EDIT-FROM-B", { timeout: 15_000 });

  // Presence (spec 54 AC6 / journey 5): each context sees the OTHER user in the
  // "online now" list (avatar by display name), and a remote-cursor caret appears
  // in the editor once the peer has placed its cursor. Presence is published via
  // Yjs awareness from the local user's identity (usePresence / OnlineUsers).
  const editorA = new EditorPage(pageA);
  const editorB = new EditorPage(pageB);
  await expect(editorA.presenceList()).toBeVisible({ timeout: 15_000 });
  await expect(editorB.presenceList()).toBeVisible({ timeout: 15_000 });
  await expect(editorA.presenceOf(runContext.userB.displayName)).toBeVisible({ timeout: 15_000 });
  await expect(editorB.presenceOf(runContext.userA.displayName)).toBeVisible({ timeout: 15_000 });
  // Each side renders the peer's remote cursor caret (y-codemirror.next awareness).
  await expect(editorA.remoteCursor().first()).toBeVisible({ timeout: 15_000 });
  await expect(editorB.remoteCursor().first()).toBeVisible({ timeout: 15_000 });

  await ctxA.close();
  await ctxB.close();
});

test("invite a collaborator through the Share modal UI @smoke", async ({
  page,
  runContext,
  seedProject,
}) => {
  // The default `page` is authenticated as the owner, User A.
  const { projectId } = await seedProject();
  const editor = new EditorPage(page);
  await editor.open(projectId);
  await editor.openFile("main.tex");

  // Invite User B as an editor through the Share dialog (exercises ShareDialog.tsx
  // in the browser, not the REST API). The invite must go through the UI.
  const share = new ShareDialog(page);
  await share.open();
  await share.invite(runContext.userB.email, "editor");
  // The owner sees the freshly-created invite listed as pending — proof the invite
  // went through the browser dialog end-to-end (createInvite → pending-invites list).
  await expect(share.pendingInvite(runContext.userB.email)).toBeVisible({ timeout: 15_000 });
});

test("a viewer cannot edit the document (read-only) @smoke", async ({
  browser,
  apiA,
  runContext,
  seedProject,
}) => {
  const { projectId } = await seedProject();
  const viewer = new ApiClient();
  await viewer.login(runContext.userB.email);
  const invite = await apiA.invite(projectId, runContext.userB.email, "viewer");
  await viewer.acceptInvite(invite.token);

  const ctxB = await browser.newContext();
  const pageB = await openDoc(ctxB, runContext.userB.email, projectId);

  // The viewer's editor mounts read-only: it is not contenteditable.
  await expect(pageB.locator(".cm-content[contenteditable='false']")).toBeVisible({
    timeout: 15_000,
  });
  await expect(pageB.locator(".cm-content[contenteditable='true']")).toHaveCount(0);

  await ctxB.close();
});
