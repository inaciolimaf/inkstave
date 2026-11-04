import { isolateHistory } from "@codemirror/commands";
import type { EditorView } from "@codemirror/view";

const BEGIN_DOCUMENT = "\\begin{document}";

/** The `\usepackage` line that loads a package, as the preamble writes it. */
export function packageLine(pkg: string): string {
  return `\\usepackage{${pkg}}`;
}

/** Whether a `\usepackage` line of the text loads the package, alone or in a list. */
export function hasPackage(text: string, pkg: string): boolean {
  return new RegExp(String.raw`\\usepackage(\[[^\]]*\])?\{[^}]*\b${pkg}\b[^}]*\}`).test(text);
}

/** Whether the text has the line that a preamble line can be added before. */
export function hasBeginDocument(view: EditorView): boolean {
  return view.state.doc.toString().includes(BEGIN_DOCUMENT);
}

/**
 * Replaces the selection with `insert` in one undoable edit and puts the cursor `cursor` characters into it.
 * The edit is isolated from the typing around it, so one Undo takes back exactly this tool's change.
 */
export function insertSnippet(view: EditorView, insert: string, cursor = insert.length): void {
  const { from, to } = view.state.selection.main;
  view.dispatch({
    changes: { from, to, insert },
    selection: { anchor: from + cursor },
    annotations: isolateHistory.of("full"),
    scrollIntoView: true,
  });
}

/** Inserts a block of lines at the cursor, starting on a line of its own. */
export function insertBlock(view: EditorView, block: string): void {
  const { from } = view.state.selection.main;
  const lineStart = view.state.doc.lineAt(from).from;
  const lead = from === lineStart ? "" : "\n";
  insertSnippet(view, `${lead}${block}\n`);
}

/** Adds a `\usepackage` line on its own line before `\begin{document}`. False when the open text has none. */
export function addPackage(view: EditorView, pkg: string): boolean {
  const index = view.state.doc.toString().indexOf(BEGIN_DOCUMENT);
  if (index < 0) return false;
  const lineStart = view.state.doc.lineAt(index).from;
  view.dispatch({
    changes: { from: lineStart, insert: `${packageLine(pkg)}\n` },
    annotations: isolateHistory.of("full"),
  });
  return true;
}
