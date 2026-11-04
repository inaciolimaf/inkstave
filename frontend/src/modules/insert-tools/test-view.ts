import { history } from "@codemirror/commands";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";

/** A real CodeMirror view with undo history, for the insert tools' tests. jsdom has no layout, so it stays unmeasured. */
export function makeView(doc: string, cursor = doc.length): EditorView {
  const parent = document.body.appendChild(document.createElement("div"));
  const state = EditorState.create({ doc, selection: { anchor: cursor }, extensions: [history()] });
  return new EditorView({ state, parent });
}
