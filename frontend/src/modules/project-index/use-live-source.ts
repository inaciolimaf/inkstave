import { Compartment, type EditorState, StateEffect } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { type MutableRefObject, useEffect, useRef, useState } from "react";

/** How long the open file's text settles before the outline parses it again (spec 111). */
export const LIVE_DEBOUNCE_MS = 300;

export interface LiveSource {
  /** The open file's text once it has settled; `null` until the first change, so the fetched copy is used. */
  text: string | null;
  /** 1-based line of the cursor, updated at once. */
  line: number;
}

function lineOf(state: EditorState): number {
  return state.doc.lineAt(state.selection.main.head).number;
}

/**
 * Follows the open file in the editor: its text, debounced, and the cursor line, at once. The listener is added
 * to the view that is already there, so the editor keeps its own configuration. Each settled text is also kept in
 * `snapshots` under its document, so the index holds the latest copy of a file the moment the writer leaves it.
 */
export function useLiveSource(
  view: EditorView | null,
  docId: string | null,
  snapshots: MutableRefObject<Map<string, string>>,
): LiveSource {
  const [live, setLive] = useState<LiveSource>({ text: null, line: 1 });
  const docRef = useRef(docId);

  useEffect(() => {
    docRef.current = docId;
    setLive((state) => (state.text === null ? state : { ...state, text: null }));
  }, [docId]);

  useEffect(() => {
    if (!view) {
      setLive({ text: null, line: 1 });
      return;
    }
    const compartment = new Compartment();
    let timer = 0;
    const settle = () => {
      const text = view.state.doc.toString();
      if (docRef.current !== null) snapshots.current.set(docRef.current, text);
      setLive((state) => ({ ...state, text }));
    };
    const listener = EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        window.clearTimeout(timer);
        timer = window.setTimeout(settle, LIVE_DEBOUNCE_MS);
      }
      if (update.docChanged || update.selectionSet) {
        const line = lineOf(update.state);
        setLive((state) => (state.line === line ? state : { ...state, line }));
      }
    });
    view.dispatch({ effects: StateEffect.appendConfig.of(compartment.of(listener)) });
    setLive((state) => ({ ...state, line: lineOf(view.state) }));
    return () => {
      window.clearTimeout(timer);
      try {
        view.dispatch({ effects: compartment.reconfigure([]) });
      } catch {
        /* the view was destroyed with its editor */
      }
    };
  }, [view, snapshots]);

  return live;
}
