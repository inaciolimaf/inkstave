import { history } from "@codemirror/commands";
import { bracketMatching, defaultHighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { Compartment, EditorState, type Extension } from "@codemirror/state";
import { oneDark } from "@codemirror/theme-one-dark";
import {
  EditorView,
  drawSelection,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  lineNumbers,
} from "@codemirror/view";
import { useEffect, useRef } from "react";

import { latex } from "./latex-language";
import { lintGutterExtension } from "./diagnostics";
import { keymapExtension } from "./keymap-extension";
import { syncHighlightExtension } from "./sync-decoration";
import type { EditorSettings } from "./types";

function fontTheme(size: number): Extension {
  return EditorView.theme({
    "&": { fontSize: `${size}px` },
    ".cm-content": { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" },
  });
}

function editableExtension(editable: boolean): Extension {
  if (editable) {
    return EditorView.contentAttributes.of({ "aria-label": "LaTeX editor" });
  }
  return [
    EditorState.readOnly.of(true),
    EditorView.editable.of(false),
    EditorView.contentAttributes.of({ "aria-label": "LaTeX editor", "aria-readonly": "true" }),
  ];
}

export function CodeMirrorEditor({
  doc,
  settings,
  dark,
  editable = false,
  onChange,
  onBlur,
  onView,
  collabExtension,
}: {
  doc: string;
  settings: EditorSettings;
  dark: boolean;
  editable?: boolean;
  onChange?: (text: string) => void;
  onBlur?: () => void;
  /** Exposes the EditorView for imperative use (SyncTeX reveal); null on unmount. */
  onView?: (view: EditorView | null) => void;
  /**
   * The `y-codemirror.next` collab binding (spec 31). When present the editor's
   * content is owned by the CRDT, so `doc`/`onChange` are not used to seed or
   * push text.
   */
  collabExtension?: Extension;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const callbacks = useRef({ onChange, onBlur, onView });
  callbacks.current = { onChange, onBlur, onView };
  const compartments = useRef({
    theme: new Compartment(),
    font: new Compartment(),
    wrap: new Compartment(),
    keys: new Compartment(),
    editable: new Compartment(),
  });

  // Create the view exactly once; later changes go through compartments/dispatch.
  useEffect(() => {
    const c = compartments.current;
    const state = EditorState.create({
      // In collab mode the CRDT seeds the content; start empty.
      doc: collabExtension ? "" : doc,
      extensions: [
        lineNumbers(),
        highlightActiveLineGutter(),
        highlightSpecialChars(),
        history(),
        drawSelection(),
        bracketMatching(),
        highlightActiveLine(),
        syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
        latex(),
        syncHighlightExtension,
        lintGutterExtension,
        ...(collabExtension ? [collabExtension] : []),
        EditorView.updateListener.of((u) => {
          if (u.docChanged) callbacks.current.onChange?.(u.state.doc.toString());
        }),
        EditorView.domEventHandlers({
          blur: () => {
            callbacks.current.onBlur?.();
            return false;
          },
        }),
        c.editable.of(editableExtension(editable)),
        c.keys.of(keymapExtension(settings.keymap)),
        c.font.of(fontTheme(settings.fontSize)),
        c.wrap.of(settings.lineWrapping ? EditorView.lineWrapping : []),
        c.theme.of(dark ? oneDark : []),
      ],
    });
    const view = new EditorView({ state, parent: hostRef.current! });
    viewRef.current = view;
    callbacks.current.onView?.(view);
    return () => {
      callbacks.current.onView?.(null);
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Swap content when the source-of-truth text changes (document switch or a
  // conflict reload) — reconfigure, never recreate. User typing does NOT change
  // `doc`, so this does not fight the editor.
  useEffect(() => {
    const view = viewRef.current;
    if (!view || collabExtension) return; // in collab mode the CRDT owns the content
    if (view.state.doc.toString() !== doc) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: doc } });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: compartments.current.editable.reconfigure(editableExtension(editable)),
    });
  }, [editable]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: compartments.current.font.reconfigure(fontTheme(settings.fontSize)),
    });
  }, [settings.fontSize]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: compartments.current.keys.reconfigure(keymapExtension(settings.keymap)),
    });
  }, [settings.keymap]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: compartments.current.wrap.reconfigure(
        settings.lineWrapping ? EditorView.lineWrapping : [],
      ),
    });
  }, [settings.lineWrapping]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: compartments.current.theme.reconfigure(dark ? oneDark : []),
    });
  }, [dark]);

  return <div ref={hostRef} className="h-full overflow-auto text-sm" data-testid="cm-host" />;
}
