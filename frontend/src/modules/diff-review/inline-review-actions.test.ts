/** The decisions of a review: what each writes, what it records, and when it ends (spec 110). */
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api-client";

import { createYDocBridge } from "./crdt-apply";
import { createReviewActions, type ReviewDeps } from "./inline-review-actions";
import { inlineReviewExtension, inlineReviewField, startInlineReview } from "./inline-review-extension";
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

const TEXT = "a\nb\nc\n";
const REPLACE_B = hunk("h1", 2, [
  ["del", "b"],
  ["add", "B"],
]);
const REPLACE_C = hunk("h2", 3, [
  ["del", "c"],
  ["add", "C"],
]);

let view: EditorView | null = null;
afterEach(() => {
  view?.destroy();
  view = null;
  document.body.innerHTML = "";
});

/** A review on a view of `doc`, with its text in a CRDT document the decisions write to. */
function setup(hunks: DiffHunk[], options: { readOnly?: boolean; record?: ReviewDeps["record"] } = {}) {
  const bridge = createYDocBridge({ "main.tex": TEXT });
  const record = vi.fn(options.record ?? (async () => "applied"));
  const deps: ReviewDeps = {
    view: () => view,
    readLive: async (path) => (await bridge.readContent(path)) ?? "",
    write: (path, target) => bridge.applyContent(path, target),
    record,
    notify: vi.fn(),
    finished: vi.fn(),
    closed: vi.fn(),
    changed: vi.fn(),
  };
  const actions = createReviewActions(deps);
  const parent = document.createElement("div");
  document.body.appendChild(parent);
  view = new EditorView({
    state: EditorState.create({ doc: TEXT, extensions: [inlineReviewExtension] }),
    parent,
  });
  view.dispatch({
    effects: startInlineReview.of({
      proposalId: "p1",
      path: "main.tex",
      readOnly: options.readOnly ?? false,
      hunks,
      decided: {},
      actions,
    }),
  });
  return { bridge, record, deps, actions, text: () => bridge.getText("main.tex").toString() };
}

/** Lets the pending writes and the outcome settle. */
const settled = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("accepting a hunk", () => {
  it("writes that hunk as one minimal edit to the document's text", async () => {
    const { bridge, actions, text } = setup([REPLACE_B, REPLACE_C]);
    const deltas: unknown[] = [];
    bridge.getText("main.tex").observe((event) => deltas.push(event.delta));
    actions.accept("h1");
    await settled();
    expect(text()).toBe("a\nB\nc\n");
    expect(deltas).toEqual([[{ retain: 2 }, { delete: 1 }, { insert: "B" }]]);
  });

  it("changes only the accepted region, and leaves the other hunks drawn", async () => {
    const { actions, text } = setup([REPLACE_B, REPLACE_C]);
    actions.accept("h1");
    await settled();
    expect(text()).toBe("a\nB\nc\n");
    expect(view?.state.field(inlineReviewField)?.hunks.map((h) => h.decision)).toEqual(["accepted", "open"]);
  });

  it("does not write a hunk that a collaborator already changed, and only rejects it", async () => {
    const { bridge, actions, deps, record } = setup([REPLACE_B]);
    bridge.getText("main.tex").delete(2, 1);
    bridge.getText("main.tex").insert(2, "Z");
    actions.accept("h1");
    await settled();
    expect(deps.notify).toHaveBeenCalledWith("drifted");
    expect(bridge.getText("main.tex").toString()).toBe("a\nZ\nc\n");
    expect(record).not.toHaveBeenCalled();
  });
});

describe("recording the outcome", () => {
  it("rejects every hunk: the text is unchanged and the outcome is rejected", async () => {
    const { actions, record, text } = setup([REPLACE_B, REPLACE_C]);
    actions.rejectAll();
    await settled();
    expect(text()).toBe(TEXT);
    expect(record).toHaveBeenCalledWith("p1", { accepted: [], rejected: ["h1", "h2"], stale: [] });
  });

  it("stores the hunks decided one by one, with their ids", async () => {
    const { actions, record } = setup([REPLACE_B, REPLACE_C]);
    actions.accept("h1");
    actions.reject("h2");
    await settled();
    expect(record).toHaveBeenCalledWith("p1", { accepted: ["h1"], rejected: ["h2"], stale: [] });
  });

  it("closes the review once the outcome is recorded", async () => {
    const { actions, deps } = setup([REPLACE_B]);
    actions.acceptAll();
    await settled();
    expect(deps.finished).toHaveBeenCalledWith("p1", "applied");
    expect(deps.closed).toHaveBeenCalled();
  });

  it("does not record while a hunk is still open", async () => {
    const { actions, record } = setup([REPLACE_B, REPLACE_C]);
    actions.reject("h1");
    await settled();
    expect(record).not.toHaveBeenCalled();
  });

  it("takes a 409 as the outcome already stored, and closes", async () => {
    const conflict = new ApiError(409, "already", undefined, [{ status: "applied" }], "already_decided");
    const { actions, deps } = setup([REPLACE_B], { record: () => Promise.reject(conflict) });
    actions.rejectAll();
    await settled();
    expect(deps.finished).toHaveBeenCalledWith("p1", "applied");
    expect(deps.closed).toHaveBeenCalled();
  });

  it("keeps the review open and says so when the outcome cannot be saved", async () => {
    const { actions, deps } = setup([REPLACE_B], { record: () => Promise.reject(new Error("offline")) });
    actions.rejectAll();
    await settled();
    expect(deps.notify).toHaveBeenCalledWith("saveError");
    expect(deps.closed).not.toHaveBeenCalled();
  });
});

describe("a viewer", () => {
  it("decides nothing", async () => {
    const { actions, record, text } = setup([REPLACE_B], { readOnly: true });
    actions.accept("h1");
    actions.rejectAll();
    await settled();
    expect(text()).toBe(TEXT);
    expect(record).not.toHaveBeenCalled();
  });
});
