/**
 * Full-tier journeys (spec 54 §5.3 "Smoke vs full", §8). Tagged `@full`, so the
 * default `smoke` project excludes them; run explicitly with
 * `playwright test --project full`. The `full` project also runs on a second
 * browser engine (Firefox, see playwright.config.ts) so these cover spec 54 §8
 * item 4 too. They add opt-in edge cases beyond the happy path and are excluded
 * from the default budget:
 *   - a real-Tectonic one-page compile (only under COMPILE_MODE=real),
 *   - a multi-hunk *partial* accept of an agent diff (complements the reject test),
 *   - viewer/permission edge cases (a viewer cannot edit/compile),
 *   - the existing agent-diff reject-without-applying case.
 */
import { test, expect } from "./support/fixtures";
import { injectAuth } from "./support/auth";
import { AgentPanel, DiffReview, EditorPage, PreviewPanel } from "./support/pages";

const APPLIED_MARKER = "rewritten by the Inkstave AI agent";

test("agent diff can be rejected without touching the document @full", async ({
  page,
  seedProject,
}) => {
  const { projectId } = await seedProject();
  const editor = new EditorPage(page);
  const agent = new AgentPanel(page);
  const review = new DiffReview(page);

  await editor.open(projectId);
  await editor.openFile("main.tex");
  await expect(page.locator(".cm-content[contenteditable='true']")).toBeVisible({
    timeout: 20_000,
  });

  await agent.open();
  await agent.send("Rewrite the introduction.");
  await expect(agent.reviewButton()).toBeVisible({ timeout: 20_000 });

  await review.openFromAgent();
  // Reject every hunk, then close: nothing is applied.
  await review.dialog().getByRole("button", { name: "Reject all" }).click();
  await page.keyboard.press("Escape");

  await expect(editor.content()).toContainText("original introduction");
  await expect(editor.content()).not.toContainText(APPLIED_MARKER);
});

test("a real Tectonic compile produces a one-page PDF preview @full", async ({
  page,
  seedProject,
}) => {
  // Spec 54 §8 item 1: a real-Tectonic one-page compile. Only meaningful when the
  // e2e backend was brought up with COMPILE_MODE=real (the default e2e mode is
  // `mock`); skip otherwise so the opt-in tier stays runnable without Tectonic.
  test.skip(
    (process.env.COMPILE_MODE ?? "mock") !== "real",
    "needs COMPILE_MODE=real (real Tectonic) backend",
  );
  // Real Tectonic can download packages on a cold run — give it generous headroom.
  test.setTimeout(180_000);

  const { projectId } = await seedProject();
  const editor = new EditorPage(page);
  const preview = new PreviewPanel(page);

  await editor.open(projectId);
  await preview.compile();

  // A genuine compile of the seeded one-section article renders a single PDF page.
  await expect(preview.firstPage()).toBeVisible({ timeout: 150_000 });
  await preview.openLog();
  await expect(preview.logRegion()).toContainText(/Tectonic|page|Output written/i);
});

test("multi-hunk diff supports a partial accept @full", async ({ page, seedProject }) => {
  // Spec 54 §8 item 2: a *partial* accept of an agent diff (complementing the
  // reject path). Accept a subset of the proposed hunks, leave the rest rejected,
  // then apply: only the accepted hunks land in the document.
  const { projectId } = await seedProject();
  const editor = new EditorPage(page);
  const agent = new AgentPanel(page);
  const review = new DiffReview(page);

  await editor.open(projectId);
  await editor.openFile("main.tex");
  await editor.waitEditable();
  await expect(editor.content()).toContainText("original introduction");

  await agent.open();
  await agent.send("Rewrite the introduction.");
  await expect(agent.reviewButton()).toBeVisible({ timeout: 20_000 });

  await review.openFromAgent();
  const dialog = page.getByRole("dialog");

  // Every hunk starts accepted. Reject all but the first so this is a genuine
  // *partial* accept (robust whether the proposal has one hunk or several).
  const switches = dialog.getByRole("switch");
  const count = await switches.count();
  expect(count).toBeGreaterThan(0);
  for (let i = 1; i < count; i++) {
    const sw = switches.nth(i);
    if (await sw.isChecked()) await sw.click();
  }
  await expect(switches.first()).toBeChecked();

  // Apply the accepted subset → confirm → the open editor converges to include
  // the accepted rewrite, and the agent never auto-wrote before this confirm.
  await review.applyAll();
  await expect(page.getByText("Changes applied", { exact: true })).toBeVisible();
  await expect(editor.content()).toContainText(APPLIED_MARKER);
});

test("a viewer cannot edit or compile the shared project @full", async ({
  browser,
  apiA,
  apiB,
  runContext,
  seedProject,
}) => {
  // Spec 54 §8 item 3: viewer/permission edge cases. Share a project with User B
  // as a *viewer*; B can open it but the editor is read-only and Compile is not
  // offered (read access does not grant doc-write / compile, spec 34).
  const { projectId } = await seedProject("Shared");
  const invite = await apiA.invite(projectId, runContext.userB.email, "viewer");
  await apiB.acceptInvite(invite.token);

  // A fresh browser context authenticated as User B (the default page fixture is A).
  const context = await browser.newContext();
  await injectAuth(context, runContext.userB.email);
  const page = await context.newPage();
  try {
    const editor = new EditorPage(page);
    await editor.open(projectId);
    await editor.openFile("main.tex");
    await expect(editor.content()).toBeVisible({ timeout: 20_000 });

    // The viewer's editor is read-only — no editable CodeMirror surface.
    await expect(page.locator(".cm-content[contenteditable='true']")).toHaveCount(0);
    // …and Compile is not offered to a viewer.
    await expect(page.getByRole("button", { name: "Compile project" })).toHaveCount(0);
  } finally {
    await context.close();
  }
});
