import type { EditorView } from "@codemirror/view";
import { useEffect, useState } from "react";

export interface EditorSelection {
  text: string;
  /** 1-based, inclusive. */
  fromLine: number;
  toLine: number;
  /** Viewport position of the selection's start; null when it scrolled out of view. */
  anchor: { left: number; top: number } | null;
}

const SETTLE_MS = 150;
const BUTTON_HEIGHT = 36;
const BUTTON_WIDTH = 180;
const MARGIN = 8;

/** Keeps a button on screen, above the selection when there is room. */
export function placeAbove(anchor: { left: number; top: number }, viewportWidth: number) {
  return {
    left: Math.max(MARGIN, Math.min(anchor.left, viewportWidth - BUTTON_WIDTH)),
    top: Math.max(MARGIN, anchor.top - BUTTON_HEIGHT - MARGIN),
  };
}

export function readSelection(view: EditorView): EditorSelection | null {
  const { main } = view.state.selection;
  if (main.empty) return null;
  const text = view.state.sliceDoc(main.from, main.to);
  if (!text.trim()) return null;
  const start = view.coordsAtPos(main.from);
  return {
    text,
    fromLine: view.state.doc.lineAt(main.from).number,
    toLine: view.state.doc.lineAt(main.to).number,
    anchor: start ? { left: start.left, top: start.top } : null,
  };
}

/** The text selected in the editor, once the selection settles. Dragging does not re-render per pixel. */
export function useEditorSelection(view: EditorView | null) {
  const [selection, setSelection] = useState<EditorSelection | null>(null);

  useEffect(() => {
    if (!view) return;
    let timer: ReturnType<typeof setTimeout>;
    const update = () => {
      clearTimeout(timer);
      timer = setTimeout(() => setSelection(view.hasFocus ? readSelection(view) : null), SETTLE_MS);
    };
    document.addEventListener("selectionchange", update);
    view.scrollDOM.addEventListener("scroll", update, { passive: true });
    return () => {
      clearTimeout(timer);
      setSelection(null);
      document.removeEventListener("selectionchange", update);
      view.scrollDOM.removeEventListener("scroll", update);
    };
  }, [view]);

  return { selection, clearSelection: () => setSelection(null) };
}
