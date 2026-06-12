/**
 * Harness sanity (spec 54 §8): cheap, browser-free checks that the deterministic
 * stubs behave as the journeys assume — the compile mock returns a real PDF + a
 * canned log, and the LLM stub drives the agent to a proposed diff. Fast: pure
 * API calls, no page.
 */
import { test, expect } from "./support/fixtures";

test("compile mock returns a canned PDF and log @smoke", async ({ apiA, seedProject }) => {
  const { projectId } = await seedProject();
  const requested = await apiA.requestCompile(projectId);
  expect(requested.status).toBe("queued");

  const done = await apiA.waitForCompile(projectId);
  expect(done.status).toBe("success");
  expect(done.has_pdf).toBe(true);

  const pdf = await apiA.getCompilePdfBytes(projectId, done.id);
  // A real PDF: starts with "%PDF" and ends with the EOF marker.
  expect(Buffer.from(pdf.subarray(0, 5)).toString("latin1")).toBe("%PDF-");
  expect(Buffer.from(pdf).toString("latin1")).toContain("%%EOF");

  const log = await apiA.getCompileLog(projectId, done.id);
  expect(log).toMatch(/Tectonic|Output written/i);
});

test("LLM stub drives the agent to a proposed diff @smoke", async ({ apiA, seedProject }) => {
  const { projectId } = await seedProject();
  const session = await apiA.createAgentSession(projectId);
  await apiA.postAgentMessage(projectId, session.id, "Rewrite the introduction.");

  const diffs = await apiA.waitForAgentDiff(projectId, session.id);
  expect(diffs.length).toBeGreaterThan(0);
  expect(diffs[0].path).toBe("main.tex");
  expect(diffs[0].status).toBe("proposed");
  expect((diffs[0].hunks ?? []).length).toBeGreaterThan(0);
});
