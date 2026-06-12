/**
 * Journey 4 — Compile & preview (spec 54 §5.3). With COMPILE_MODE=mock the worker
 * returns a canned one-page PDF + log instantly. Clicking Compile renders the PDF
 * in the PDF.js preview and shows log output; a document with an injected LaTeX
 * error surfaces in the log and the problems annotations.
 */
import { test, expect } from "./support/fixtures";
import { EditorPage, PreviewPanel } from "./support/pages";

const ERROR_DOC =
  "\\documentclass{article}\n\\begin{document}\n\\inkstaveforceerror\n\\end{document}\n";

test("compile renders a PDF preview and log output @smoke", async ({ page, seedProject }) => {
  const { projectId } = await seedProject();
  const editor = new EditorPage(page);
  const preview = new PreviewPanel(page);

  await editor.open(projectId);
  await preview.compile();

  // The mocked PDF renders to a PDF.js page canvas.
  await expect(preview.firstPage()).toBeVisible({ timeout: 20_000 });

  // The log panel shows the (mocked) compile output.
  await preview.openLog();
  await expect(preview.logRegion()).toContainText(/Tectonic|Output written|page/i);
});

test("an injected LaTeX error surfaces in the log and annotations @smoke", async ({
  page,
  apiA,
  seedProject,
}) => {
  const { projectId, docId } = await seedProject();
  await apiA.setDocContent(projectId, docId, ERROR_DOC);

  const editor = new EditorPage(page);
  const preview = new PreviewPanel(page);
  await editor.open(projectId);
  await preview.compile();

  // The failed compile auto-loads its problems; the error surfaces as an annotation.
  // (Waiting on this also waits for the compile to reach a terminal state.)
  await expect(preview.problem("Undefined control sequence")).toBeVisible({ timeout: 25_000 });

  // A failed compile auto-expands the log too, which shows the same error.
  await expect(preview.logRegion()).toContainText("Undefined control sequence");
});
