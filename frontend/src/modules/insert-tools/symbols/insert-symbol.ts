import type { EditorView } from "@codemirror/view";

import { insertSnippet } from "../insert-text";

import { rememberRecent } from "./recent-symbols";
import type { SymbolEntry } from "./symbol-data";

/**
 * The text a symbol inserts. A command with arguments gets its `{}` and the cursor goes inside the first. A
 * command of letters gets a space when a letter follows, so `\alpha` does not run into the next word.
 */
export function symbolInsert(entry: SymbolEntry, next: string): { insert: string; cursor: number } {
  const args = entry.args ?? 0;
  if (args > 0) return { insert: `${entry.command}${"{}".repeat(args)}`, cursor: entry.command.length + 1 };
  const space = /[a-zA-Z]$/.test(entry.command) && /^[a-zA-Z]/.test(next) ? " " : "";
  const insert = `${entry.command}${space}`;
  return { insert, cursor: insert.length };
}

export function insertSymbol(view: EditorView, entry: SymbolEntry): void {
  const { to } = view.state.selection.main;
  const { insert, cursor } = symbolInsert(entry, view.state.sliceDoc(to, to + 1));
  insertSnippet(view, insert, cursor);
  rememberRecent(entry.command);
}
