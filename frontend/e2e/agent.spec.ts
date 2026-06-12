/**
 * Journey 7 — AI agent diff (spec 54 §5.3, spec 46 §8, spec 47 §8). With
 * LLM_STUB=true the agent runs a deterministic search → read → propose_edit
 * sequence and proposes a per-file diff. This exercises:
 *   - streamed assistant text appearing in the transcript (spec 46 §8a),
 *   - a tool-activity row appearing (spec 46 §8b),
 *   - the diff-review flow: reject a hunk → preview updates → re-accept → apply,
 *     asserting the accepted change is present and a rejected hunk's text is
 *     absent from the preview (spec 47 §8),
 *   - the agent never auto-writes (nothing applied until confirm), and
 *   - Stop on a run shows a cancelled marker (spec 46 §8c).
 * Everything is scripted (no real LLM/Tectonic), so it stays within the budget.
 */
import { test, expect } from "./support/fixtures";
import { AgentPanel, DiffReview, EditorPage } from "./support/pages";

// The stub rewrites the document to this marker text (testkit/llm_stub.py).
const APPLIED_MARKER = "rewritten by the Inkstave AI agent";

test("agent streams, shows tool activity, and applies a reviewed diff @smoke", async ({
  page,
  seedProject,
}) => {
  const { projectId } = await seedProject();
  const editor = new EditorPage(page);
  const agent = new AgentPanel(page);
  const review = new DiffReview(page);

  await editor.open(projectId);
  await editor.openFile("main.tex");
  await editor.waitEditable();
  await expect(editor.content()).toContainText("original introduction");

  // Ask the agent; the stub streams a reply and proposes a diff.
  await agent.open();
  await agent.send("Rewrite the introduction.");

  // (182a) Streamed assistant text appears in the transcript log.
  const transcript = page.getByRole("log", { name: "Conversation" });
  await expect(transcript.locator("[data-role='assistant']")).toContainText(
    /prepared a rewrite|searched the project/i,
    { timeout: 20_000 },
  );

  // (182b) At least one tool-activity row appears (search/read/propose_edit).
  await expect(
    transcript.getByText(/Searched the project|Read a file|Proposed an edit/),
  ).toBeVisible({
    timeout: 20_000,
  });

  // The diff proposal surfaces a Review changes button.
  await expect(agent.reviewButton()).toBeVisible({ timeout: 20_000 });

  // The agent never auto-writes: the document is unchanged before apply.
  await expect(editor.content()).toContainText("original introduction");
  await expect(editor.content()).not.toContainText(APPLIED_MARKER);

  // Open the diff-review surface.
  await review.openFromAgent();
  const dialog = page.getByRole("dialog");

  // (198) Reject the proposed hunk, then preview the file — the preview must
  // reflect the rejection: the rewritten marker is absent and the original line
  // remains. This proves the preview updates as hunks are toggled.
  const acceptSwitch = dialog.getByRole("switch").first();
  await expect(acceptSwitch).toBeChecked();
  await acceptSwitch.click();
  await expect(acceptSwitch).not.toBeChecked();

  await dialog.getByRole("button", { name: "Preview" }).first().click();
  const preview = dialog.locator("pre").first();
  await expect(preview).toContainText("original introduction");
  await expect(preview).not.toContainText(APPLIED_MARKER);

  // (198) Re-accept the hunk; the preview now reflects the accepted change.
  await dialog.getByRole("button", { name: "Diff" }).first().click();
  await acceptSwitch.click();
  await expect(acceptSwitch).toBeChecked();
  await dialog.getByRole("button", { name: "Preview" }).first().click();
  await expect(preview).toContainText(APPLIED_MARKER);
  await dialog.getByRole("button", { name: "Diff" }).first().click();

  // Apply the accepted hunk → confirm → the open editor converges to the rewrite.
  await review.applyAll();
  await expect(page.getByText("Changes applied", { exact: true })).toBeVisible();
  await expect(editor.content()).toContainText(APPLIED_MARKER);
  // (198) The previously-original paragraph text is gone (the accepted change won).
  await expect(editor.content()).not.toContainText("original introduction paragraph");
});

test("Stop cancels an in-flight run and shows a cancelled marker", async ({
  page,
  seedProject,
}) => {
  const { projectId } = await seedProject();
  const editor = new EditorPage(page);
  const agent = new AgentPanel(page);

  await editor.open(projectId);
  await editor.openFile("main.tex");
  await editor.waitEditable();

  await agent.open();
  await agent.send("Rewrite the introduction.");

  // (182c) While the run is active, Stop is offered; clicking it cancels the run
  // and a cancelled marker is shown in the transcript.
  const stop = page.getByRole("button", { name: "Stop the run" });
  await stop.click({ timeout: 20_000 });

  await expect(page.getByText("Run cancelled").first()).toBeVisible({ timeout: 20_000 });
});
