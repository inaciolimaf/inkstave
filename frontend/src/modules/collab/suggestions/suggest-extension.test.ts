/**
 * The editor side of Suggesting mode with a real EditorView, a local Y.Doc and y-codemirror.next's undo (spec 119
 * §5.3, §8): the text and its record are written together, one undo reverts both, and a refused edit leaves
 * the text as it was.
 */
import type { Extension } from "@codemirror/state";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterEach, describe, expect, it } from "vitest";
import { ySync, yCollab } from "y-codemirror.next";
import { Awareness } from "y-protocols/awareness";
import * as Y from "yjs";

import { SUGGESTION_TEXT_MAX_CHARS, encodePosition } from "./model";
import type { SuggestionFields, SuggestionMap } from "./model";
import { SuggestController, suggestExtension } from "./suggest-extension";

interface Harness {
  doc: Y.Doc;
  text: Y.Text;
  map: SuggestionMap;
  view: EditorView;
  undo: Y.UndoManager;
  controller: SuggestController;
  blocked: () => number;
}

const AUTHOR = { id: "b", name: "B" };
let harness: Harness | null = null;

afterEach(() => {
  if (harness) {
    harness.view.destroy();
    harness.doc.destroy();
    harness.view.dom.remove();
  }
  harness = null;
});

function setup(initial: string, suggesting: boolean): Harness {
  const doc = new Y.Doc();
  const text = doc.getText("content");
  const map = doc.getMap<SuggestionFields>("suggestions");
  text.insert(0, initial);
  const undo = new Y.UndoManager([text, map]);
  const awareness = new Awareness(doc);
  const controller = new SuggestController(() => AUTHOR, awareness);
  controller.setEnabled(true);
  controller.setSuggesting(suggesting);
  let blockedCount = 0;
  controller.onBlocked = () => {
    blockedCount += 1;
  };
  // The library returns its plugins as an array; the sync plugin is replaced by Suggesting mode's.
  const collab = yCollab(text, awareness, { undoManager: undo }) as Extension[];
  const extensions: Extension[] = [
    ...collab.filter((extension) => extension !== ySync),
    suggestExtension({ ytext: text, suggestions: map, controller, canDecide: true }),
  ];
  const parent = document.createElement("div");
  document.body.appendChild(parent);
  const view = new EditorView({ state: EditorState.create({ doc: text.toString(), extensions }), parent });
  harness = { doc, text, map, view, undo, controller, blocked: () => blockedCount };
  return harness;
}

function type(view: EditorView, from: number, insert: string): void {
  view.dispatch({ changes: { from, insert }, userEvent: "input.type" });
}

function removeRange(view: EditorView, from: number, to: number): void {
  view.dispatch({ changes: { from, to, insert: "" }, userEvent: "delete.backward" });
}

describe("Suggesting mode in the editor", () => {
  it("records typed text as an insertion of its author, and the text holds it", () => {
    const h = setup("the important point", true);
    type(h.view, 4, "very ");
    expect(h.view.state.doc.toString()).toBe("the very important point");
    expect(h.text.toString()).toBe("the very important point");
    const records = [...h.map.values()];
    expect(records).toHaveLength(1);
    expect(records[0]).toMatchObject({ kind: "insert", author_id: "b", author_name: "B" });
  });

  it("typing at the end of its own insertion grows it, with no second record", () => {
    const h = setup("the important point", true);
    type(h.view, 4, "very ");
    type(h.view, 9, "really ");
    expect(h.text.toString()).toBe("the very really important point");
    expect(h.map.size).toBe(1);
  });

  it("records deleted text as a deletion with the removed text, and the text loses it", () => {
    const h = setup("the old important point", true);
    removeRange(h.view, 4, 8);
    expect(h.text.toString()).toBe("the important point");
    const records = [...h.map.values()];
    expect(records).toEqual([expect.objectContaining({ kind: "delete", author_id: "b", text: "old " })]);
  });

  it("one undo reverts a suggested deletion: the text is back and the record is gone", () => {
    const h = setup("the old important point", true);
    removeRange(h.view, 4, 8);
    h.undo.undo();
    expect(h.text.toString()).toBe("the old important point");
    expect(h.view.state.doc.toString()).toBe("the old important point");
    expect(h.map.size).toBe(0);
  });

  it("one undo reverts a suggested insertion: the text and the record go together", () => {
    const h = setup("the important point", true);
    type(h.view, 4, "very ");
    h.undo.undo();
    expect(h.text.toString()).toBe("the important point");
    expect(h.map.size).toBe(0);
  });

  it("with Suggesting off, edits are plain: no record, even inside someone's suggestion", () => {
    const h = setup("the old important point", true);
    removeRange(h.view, 4, 8);
    h.controller.setSuggesting(false);
    type(h.view, 4, "new ");
    expect(h.text.toString()).toBe("the new important point");
    expect(h.map.size).toBe(1);
    expect([...h.map.values()][0]).toMatchObject({ kind: "delete", text: "old " });
  });

  it("a deletion too large to record is refused and the text stays", () => {
    const big = "x".repeat(SUGGESTION_TEXT_MAX_CHARS + 1);
    const h = setup(big, true);
    removeRange(h.view, 0, big.length);
    expect(h.view.state.doc.length).toBe(big.length);
    expect(h.text.toString()).toBe(big);
    expect(h.blocked()).toBe(1);
    expect(h.map.size).toBe(0);
  });

  it("a remote edit reaches the view without being written back as a suggestion", () => {
    const h = setup("the point", true);
    h.text.insert(0, "Hi. ");
    expect(h.view.state.doc.toString()).toBe("Hi. the point");
    expect(h.map.size).toBe(0);
  });

  it("a suggestion that arrives from another peer is drawn in the text", () => {
    const h = setup("the old point", true);
    h.map.set("remote", {
      kind: "delete",
      author_id: "c",
      author_name: "C",
      created_at: "2026-11-04T10:00:00.000Z",
      at: encodePosition(h.text, 4, 0),
      text: "gone ",
    });
    expect(h.view.dom.querySelector(".cm-suggest-delete")).not.toBeNull();
  });
});
