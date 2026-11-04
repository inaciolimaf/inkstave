/**
 * Journey 7 — AI agent diff (spec 54 §5.3, spec 46 §8, spec 47 §8, spec 110). With
 * LLM_STUB=true the agent runs a deterministic search → read → propose_edit
 * sequence and proposes a per-file diff. This exercises:
 *   - streamed assistant text appearing in the transcript (spec 46 §8a),
 *   - a tool-activity row appearing (spec 46 §8b),
 *   - the inline review (spec 110): the change is drawn in the text, accepting it
 *     writes it, and after a reload the card says it was applied and no review
 *     is offered again,
 *   - the agent never auto-writes (nothing changes before the accept), and
 *   - Stop on a run shows a cancelled marker (spec 46 §8c).
 * Everything is scripted (no real LLM/Tectonic), so it stays within the budget.
 */
import { test, expect } from "../support/fixtures";
import { AgentPanel, EditorPage, InlineReview } from "../support/pages";

// The stub rewrites the document to this marker text (testkit/llm_stub.py).
const APPLIED_MARKER = "rewritten by the Inkstave AI agent";

test("agent streams, shows tool activity, and applies a change reviewed in the text @smoke", async ({
  page,
  seedProject,
}) => {
  const { projectId } = await seedProject();
  const editor = new EditorPage(page);
  const agent = new AgentPanel(page);
  const review = new InlineReview(page);

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

  // (182b) The tool activity folds into one line (spec 107): the running tool's
  // label, then the step count once the run settles.
  await expect(
    transcript.getByText(/Searched the project|Read a file|Proposed an edit|\d+ steps?/).first(),
  ).toBeVisible({ timeout: 20_000 });

  // The diff proposal surfaces a Review changes button.
  await expect(agent.reviewButton()).toBeVisible({ timeout: 20_000 });

  // The agent never auto-writes: the document is unchanged before a decision.
  await expect(editor.content()).toContainText("original introduction");
  await expect(editor.content()).not.toContainText(APPLIED_MARKER);

  // The change is drawn in the text; accepting it writes it and the open editor converges.
  await review.openFromAgent();
  await review.accept(1);
  await expect(editor.content()).toContainText(APPLIED_MARKER);
  await expect(editor.content()).not.toContainText("original introduction paragraph");

  // The outcome is stored: after a reload the card says so, and no review is offered again.
  await page.reload();
  await editor.openFile("main.tex");
  await editor.waitEditable();
  await agent.open();
  await agent.openPreviousSession();
  await expect(page.getByText("Applied", { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(agent.reviewButton()).toHaveCount(0);
});

test("Stop cancels an in-flight run and shows a cancelled marker", async ({ page, seedProject }) => {
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
