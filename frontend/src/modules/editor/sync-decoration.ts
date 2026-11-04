/**
 * CodeMirror 6 extension + helpers for SyncTeX "reveal a source line" (spec 26).
 *
 * A line decoration flashes the synced line (warning tint, ~1.2s) and the editor scrolls
 * to it; the flash is never the only signal (the cursor/scroll also move).
 */
import { StateEffect, StateField } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView } from "@codemirror/view";

import type { TreeNode } from "@/modules/file-tree";

const FLASH_MS = 1200;

/** Set (line number, 1-based) or clear (null) the sync-flash decoration. */
export const setSyncLine = StateEffect.define<number | null>();

const syncLineField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(deco, tr) {
    deco = deco.map(tr.changes);
    for (const effect of tr.effects) {
      if (effect.is(setSyncLine)) {
        if (effect.value == null) {
          deco = Decoration.none;
        } else {
          const lineNo = Math.max(1, Math.min(effect.value, tr.state.doc.lines));
          const line = tr.state.doc.line(lineNo);
          deco = Decoration.set([Decoration.line({ class: "cm-sync-flash" }).range(line.from)]);
        }
      }
    }
    return deco;
  },
  provide: (field) => EditorView.decorations.from(field),
});

const syncFlashTheme = EditorView.baseTheme({
  ".cm-sync-flash": {
    backgroundColor: "hsl(var(--warning) / 0.25)",
    transition: "background-color var(--motion-base) var(--ease-out)",
  },
});

/** The extension bundle to add to the editor's state. */
export const syncHighlightExtension = [syncLineField, syncFlashTheme];

/** 1-based line of the primary cursor. */
export function cursorLine(view: EditorView): number {
  return view.state.doc.lineAt(view.state.selection.main.head).number;
}

/** A stretch of a line to select on arrival: a search match (spec 122). */
export interface LineSpan {
  column: number;
  length: number;
}

/** Scroll to `line`, place the cursor there (or select `span` in it), and flash it (auto-clearing). */
export function revealLine(view: EditorView, line: number, span?: LineSpan): void {
  const lineNo = Math.max(1, Math.min(line, view.state.doc.lines));
  const target = view.state.doc.line(lineNo);
  const pos = target.from + Math.min(span?.column ?? 0, target.length);
  const head = span ? Math.min(pos + span.length, view.state.doc.length) : pos;
  view.dispatch({
    selection: { anchor: pos, head },
    effects: [EditorView.scrollIntoView(pos, { y: "center" }), setSyncLine.of(lineNo)],
    scrollIntoView: true,
  });
  window.setTimeout(() => {
    // The view may have been torn down by the time the flash expires.
    try {
      view.dispatch({ effects: setSyncLine.of(null) });
    } catch {
      /* view destroyed */
    }
  }, FLASH_MS);
}

/** Find a tree node by its project-relative path (for cross-file sync jumps). */
export function findNodeByPath(root: TreeNode, path: string): TreeNode | null {
  if (root.path === path) return root;
  for (const child of root.children) {
    const hit = findNodeByPath(child, path);
    if (hit) return hit;
  }
  return null;
}
