/** The review drawn in the text: placement, what is drawn, blocked hunks after an edit, and the keys (spec 110). */
import { EditorState } from "@codemirror/state";
import { EditorView, runScopeHandlers } from "@codemirror/view";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ReviewActions } from "./inline-review-model";
import {
  type InlineReview,
  inlineReviewExtension,
  inlineReviewField,
  startInlineReview,
} from "./inline-review-extension";
import type { DiffHunk, LineType } from "./types";

function hunk(id: string, oldStart: number, lines: [LineType, string][]): DiffHunk {
  return {
    id,
    header: `@@ -${oldStart} @@`,
    oldStart,
    oldLines: lines.filter(([t]) => t !== "add").length,
    newStart: oldStart,
    newLines: lines.filter(([t]) => t !== "del").length,
    lines: lines.map(([type, text]) => ({ type, text })),
  };
}

const REPLACE_B = hunk("h1", 2, [
  ["del", "b"],
  ["add", "B"],
]);
const REPLACE_C = hunk("h2", 3, [
  ["del", "c"],
  ["add", "C"],
]);

function noopActions(): ReviewActions {
  return {
    accept: vi.fn(),
    reject: vi.fn(),
    acceptAll: vi.fn(),
    rejectAll: vi.fn(),
    settle: vi.fn(),
    close: vi.fn(),
    onChange: vi.fn(),
  };
}

let view: EditorView | null = null;
afterEach(() => {
  view?.destroy();
  view = null;
  document.body.innerHTML = "";
});

function open(
  doc: string,
  hunks: DiffHunk[],
  options: { readOnly?: boolean; actions?: ReviewActions; decided?: Record<string, "accepted"> } = {},
) {
  const parent = document.createElement("div");
  document.body.appendChild(parent);
  view = new EditorView({ state: EditorState.create({ doc, extensions: [inlineReviewExtension] }), parent });
  view.dispatch({
    effects: startInlineReview.of({
      proposalId: "p1",
      path: "main.tex",
      readOnly: options.readOnly ?? false,
      hunks,
      decided: options.decided ?? {},
      actions: options.actions ?? noopActions(),
    }),
  });
  return view;
}

function reviewOf(v: EditorView): InlineReview {
  const review = v.state.field(inlineReviewField);
  if (!review) throw new Error("no review");
  return review;
}

/** Every decoration in the text, with the class it carries if it is a line mark. */
function drawn(v: EditorView) {
  const found: { from: number; to: number; cls?: string; widget: boolean }[] = [];
  reviewOf(v).decorations.between(0, v.state.doc.length, (from, to, value) => {
    const spec = value.spec as { class?: string; widget?: unknown };
    found.push({ from, to, cls: spec.class, widget: spec.widget !== undefined });
  });
  return found;
}

describe("placement", () => {
  it("places each hunk on its old lines, in the text as it is", () => {
    const v = open("a\nb\nc\n", [REPLACE_B, REPLACE_C]);
    const [first, second] = reviewOf(v).hunks;
    expect(first).toMatchObject({ line: 1, blocked: false, from: 2, to: 3 });
    expect(second).toMatchObject({ line: 2, blocked: false, from: 4, to: 5 });
  });

  it("draws a toolbar, the removed line and the added text for an open hunk", () => {
    const v = open("a\nb\nc\n", [REPLACE_B]);
    const marks = drawn(v);
    expect(marks.filter((m) => m.widget)).toHaveLength(2);
    const removed = marks.find((m) => m.cls?.includes("cm-review-removed"));
    expect(removed).toMatchObject({ from: 2 });
  });

  it("draws nothing in the text until a review starts", () => {
    const parent = document.createElement("div");
    view = new EditorView({
      state: EditorState.create({ doc: "a\nb\n", extensions: [inlineReviewExtension] }),
      parent,
    });
    expect(view.state.field(inlineReviewField)).toBeNull();
    expect(view.contentDOM.querySelectorAll(".cm-review-toolbar")).toHaveLength(0);
  });

  it("does not draw a hunk decided on an earlier opening, and keeps the others", () => {
    const v = open("a\nb\nc\n", [REPLACE_B, REPLACE_C], { decided: { h1: "accepted" } });
    expect(reviewOf(v).hunks.map((h) => h.decision)).toEqual(["accepted", "open"]);
    expect(v.contentDOM.querySelectorAll(".cm-review-toolbar")).toHaveLength(1);
    expect(drawn(v).some((m) => m.from === 2)).toBe(false);
  });

  it("does not change the document", () => {
    const v = open("a\nb\nc\n", [REPLACE_B, REPLACE_C]);
    expect(v.state.doc.toString()).toBe("a\nb\nc\n");
  });
});

describe("live edits", () => {
  it("keeps a hunk acceptable when an edit happens elsewhere in the text", () => {
    const v = open("a\nb\nc\n", [REPLACE_B]);
    v.dispatch({ changes: { from: 0, to: 0, insert: "x\n" } });
    expect(reviewOf(v).hunks[0]).toMatchObject({ blocked: false });
    expect(v.state.doc.toString()).toBe("x\na\nb\nc\n");
  });

  it("turns a hunk blocked when an edit lands inside its old lines", () => {
    const v = open("a\nb\nc\n", [REPLACE_B]);
    const line = v.state.doc.line(2);
    v.dispatch({ changes: { from: line.from, to: line.to, insert: "DIFFERENT" } });
    expect(reviewOf(v).hunks[0]).toMatchObject({ blocked: true });
    // A blocked hunk is drawn with its toolbar only: no removed line, no added text.
    expect(drawn(v).some((m) => m.cls?.includes("cm-review-removed"))).toBe(false);
  });

  it("finds a blocked hunk again once its old lines reappear", () => {
    const v = open("a\nDIFFERENT\nc\n", [REPLACE_B]);
    expect(reviewOf(v).hunks[0]).toMatchObject({ blocked: true });
    v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: "a\nb\nc\n" } });
    expect(reviewOf(v).hunks[0]).toMatchObject({ blocked: false, line: 1 });
  });
});

describe("viewers and keys", () => {
  it("gives a viewer the changes drawn but no controls", () => {
    const v = open("a\nb\nc\n", [REPLACE_B], { readOnly: true });
    expect(drawn(v).some((m) => m.cls?.includes("cm-review-removed"))).toBe(true);
    expect(v.contentDOM.querySelectorAll("button")).toHaveLength(0);
  });

  it("gives an open hunk Accept and Reject buttons, labelled for the screen reader", () => {
    const v = open("a\nb\nc\n", [REPLACE_B]);
    const labels = [...v.contentDOM.querySelectorAll("button")].map((b) => b.getAttribute("aria-label"));
    expect(labels).toEqual(["Accept change 1", "Reject change 1"]);
  });

  it("walks the open hunks with Alt+] and Alt+[", () => {
    const v = open("a\nb\nc\n", [REPLACE_B, REPLACE_C]);
    expect(reviewOf(v).active).toBe(0);
    runScopeHandlers(v, new KeyboardEvent("keydown", { key: "]", altKey: true }), "editor");
    expect(reviewOf(v).active).toBe(1);
    runScopeHandlers(v, new KeyboardEvent("keydown", { key: "[", altKey: true }), "editor");
    expect(reviewOf(v).active).toBe(0);
  });

  it("decides the current hunk with Alt+Enter and Alt+Backspace", () => {
    const actions = noopActions();
    const v = open("a\nb\nc\n", [REPLACE_B, REPLACE_C], { actions });
    runScopeHandlers(v, new KeyboardEvent("keydown", { key: "Enter", altKey: true }), "editor");
    expect(actions.accept).toHaveBeenCalledWith("h1");
    runScopeHandlers(v, new KeyboardEvent("keydown", { key: "Backspace", altKey: true }), "editor");
    expect(actions.reject).toHaveBeenCalledWith("h1");
  });

  it("leaves the keys alone for a viewer", () => {
    const actions = noopActions();
    const v = open("a\nb\nc\n", [REPLACE_B], { readOnly: true, actions });
    runScopeHandlers(v, new KeyboardEvent("keydown", { key: "Enter", altKey: true }), "editor");
    expect(actions.accept).not.toHaveBeenCalled();
  });
});
