/** The highlight in the editor: it follows its text, and a click selects its thread (spec 118, AC 1, 2, 3). */
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import * as Y from "yjs";
import { afterEach, describe, expect, it, vi } from "vitest";

import { encodeAnchor } from "./anchors";
import { type CommentMarkHandlers, commentMarks, setCommentMarks } from "./comment-marks";

const BODY = "Intro.\n\nWe read the results and they were clear.\n";

let view: EditorView | null = null;

afterEach(() => {
  view?.destroy();
  view = null;
});

function editorWith(text: Y.Text, handlers: { current: CommentMarkHandlers }): EditorView {
  const state = EditorState.create({ doc: text.toString(), extensions: [commentMarks(text, handlers)] });
  view = new EditorView({ state, parent: document.body });
  return view;
}

function markFor(id: string, anchorsOf: Y.Text, from: number, to: number) {
  const anchors = encodeAnchor(anchorsOf, from, to);
  return { id, anchorStart: anchors.anchorStart, anchorEnd: anchors.anchorEnd };
}

function highlighted(editor: EditorView, id: string): string | null {
  return editor.contentDOM.querySelector(`[data-thread-id="${id}"]`)?.textContent ?? null;
}

describe("comment marks", () => {
  it("highlights the anchored text", () => {
    const text = new Y.Doc().getText("content");
    text.insert(0, BODY);
    const editor = editorWith(text, { current: { onSelect: vi.fn(), onNew: () => false } });
    const from = BODY.indexOf("the results");

    editor.dispatch({
      effects: setCommentMarks.of({ marks: [markFor("t1", text, from, from + 11)], selectedId: null }),
    });

    expect(highlighted(editor, "t1")).toBe("the results");
  });

  it("keeps the highlight on its text when text is typed before it", () => {
    const doc = new Y.Doc();
    const text = doc.getText("content");
    text.insert(0, BODY);
    const editor = editorWith(text, { current: { onSelect: vi.fn(), onNew: () => false } });
    const from = BODY.indexOf("the results");
    editor.dispatch({
      effects: setCommentMarks.of({ marks: [markFor("t1", text, from, from + 11)], selectedId: null }),
    });

    text.insert(0, "A new sentence. ");
    editor.dispatch({ changes: { from: 0, insert: "A new sentence. " } });

    expect(highlighted(editor, "t1")).toBe("the results");
  });

  it("does not take text typed at the end of the range into the highlight", () => {
    const text = new Y.Doc().getText("content");
    text.insert(0, BODY);
    const editor = editorWith(text, { current: { onSelect: vi.fn(), onNew: () => false } });
    const from = BODY.indexOf("the results");
    const to = from + 11;
    editor.dispatch({
      effects: setCommentMarks.of({ marks: [markFor("t1", text, from, to)], selectedId: null }),
    });

    text.insert(to, " typed");
    editor.dispatch({ changes: { from: to, insert: " typed" } });

    expect(highlighted(editor, "t1")).toBe("the results");
  });

  it("selects the thread when its highlight is clicked", () => {
    const onSelect = vi.fn();
    const text = new Y.Doc().getText("content");
    text.insert(0, BODY);
    const editor = editorWith(text, { current: { onSelect, onNew: () => false } });
    const from = BODY.indexOf("the results");
    editor.dispatch({
      effects: setCommentMarks.of({ marks: [markFor("t9", text, from, from + 11)], selectedId: null }),
    });

    const mark = editor.contentDOM.querySelector('[data-thread-id="t9"]');
    mark?.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));

    expect(onSelect).toHaveBeenCalledWith("t9");
  });

  it("drops the highlight of a thread whose text was removed", () => {
    const text = new Y.Doc().getText("content");
    text.insert(0, BODY);
    const editor = editorWith(text, { current: { onSelect: vi.fn(), onNew: () => false } });
    const from = BODY.indexOf("the results");
    editor.dispatch({
      effects: setCommentMarks.of({ marks: [markFor("t1", text, from, from + 11)], selectedId: null }),
    });

    text.delete(from, 11);
    editor.dispatch({ changes: { from, to: from + 11 } });

    expect(highlighted(editor, "t1")).toBeNull();
  });
});
