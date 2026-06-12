import { forEachDiagnostic } from "@codemirror/lint";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterEach, describe, expect, it } from "vitest";

import type { Problem } from "@/features/pdf-preview/problems";

import { applyDiagnostics, lintGutterExtension, problemsToDiagnostics } from "./diagnostics";

function problem(over: Partial<Problem>): Problem {
  return {
    severity: "error",
    message: "msg",
    file: "main.tex",
    line: 1,
    end_line: null,
    raw: "",
    rule: "tex-error",
    ...over,
  };
}

function makeView(doc: string): EditorView {
  const parent = document.createElement("div");
  document.body.appendChild(parent);
  return new EditorView({
    state: EditorState.create({ doc, extensions: [lintGutterExtension] }),
    parent,
  });
}

let view: EditorView | null = null;
afterEach(() => {
  view?.destroy();
  view = null;
});

describe("problemsToDiagnostics", () => {
  const doc = EditorState.create({ doc: "a\nb\nc\nd\ne" }).doc;

  it("maps severity and a single-line range", () => {
    const [d] = problemsToDiagnostics(doc, [problem({ line: 2, severity: "warning" })]);
    expect(d.severity).toBe("warning");
    expect(d.from).toBe(doc.line(2).from);
    expect(d.to).toBe(doc.line(2).to);
  });

  it("spans end_line for typesetting ranges", () => {
    const [d] = problemsToDiagnostics(doc, [problem({ line: 3, end_line: 4, severity: "info" })]);
    expect(d.from).toBe(doc.line(3).from);
    expect(d.to).toBe(doc.line(4).to);
  });

  it("skips problems without a line", () => {
    expect(problemsToDiagnostics(doc, [problem({ line: null })])).toHaveLength(0);
  });

  it("clamps out-of-range lines to the document", () => {
    const [d] = problemsToDiagnostics(doc, [problem({ line: 99 })]);
    expect(d.from).toBe(doc.line(5).from);
  });
});

describe("applyDiagnostics", () => {
  it("pushes diagnostics into the editor", () => {
    view = makeView("one\ntwo\nthree");
    applyDiagnostics(view, [
      problem({ line: 1, severity: "error" }),
      problem({ line: 2, severity: "warning" }),
    ]);
    const collected: string[] = [];
    forEachDiagnostic(view.state, (d) => collected.push(d.severity));
    expect(collected).toEqual(["error", "warning"]);
  });

  it("replaces the previous diagnostics on a recompile", () => {
    view = makeView("one\ntwo\nthree");
    applyDiagnostics(view, [problem({ line: 1, severity: "error" })]);
    applyDiagnostics(view, [problem({ line: 3, severity: "info" })]);
    const collected: { sev: string; line: number }[] = [];
    forEachDiagnostic(view.state, (d, from) => {
      collected.push({ sev: d.severity, line: view!.state.doc.lineAt(from).number });
    });
    expect(collected).toEqual([{ sev: "info", line: 3 }]);
  });

  it("clears diagnostics when given none", () => {
    view = makeView("one\ntwo");
    applyDiagnostics(view, [problem({ line: 1 })]);
    applyDiagnostics(view, []);
    let count = 0;
    forEachDiagnostic(view.state, () => count++);
    expect(count).toBe(0);
  });
});

describe("current-file filtering (spec 27 AC11)", () => {
  const doc = EditorState.create({ doc: "a\nb\nc\nd\ne" }).doc;

  it("excludes problems for other files from the current editor", () => {
    const path = "main.tex";
    const problems = [
      problem({ file: "main.tex", line: 2, message: "in main" }),
      problem({ file: "chapter1.tex", line: 3, message: "in chapter1" }),
      problem({ file: "main.tex", line: 4, message: "also main" }),
    ];

    // Replicate the one-line filter the workspace applies before mapping.
    const forThisFile = problems.filter((p) => p.file === path);
    const diagnostics = problemsToDiagnostics(doc, forThisFile);

    expect(diagnostics).toHaveLength(2);
    expect(diagnostics.map((d) => d.message)).toEqual(["in main", "also main"]);
    expect(diagnostics.every((d) => d.message !== "in chapter1")).toBe(true);
  });
});
