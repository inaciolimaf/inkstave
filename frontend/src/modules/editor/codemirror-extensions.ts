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
import type { RefObject } from "react";

import { lintGutterExtension } from "./diagnostics";
import { keymapExtension } from "./keymap-extension";
import { latex } from "./latex-language";
import { syncHighlightExtension } from "./sync-decoration";
import type { EditorSettings } from "./types";

const SHEET = "hsl(var(--background))";
const TINT = "hsl(var(--foreground) / 0.05)";
const SELECTION = "hsl(var(--foreground) / 0.16)";
const SELECTION_SELECTORS =
  "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection";

/**
 * The sheet (spec 106): paper in light and carbon in dark, from the page's own tokens, which follow the
 * same preference as `dark`. One Dark's syntax colours are a separate highlight style and stay.
 */
const sheetTheme = EditorView.theme({
  "&": { backgroundColor: SHEET, color: "hsl(var(--foreground))" },
  ".cm-gutters": {
    backgroundColor: SHEET,
    color: "hsl(var(--muted-foreground))",
    borderRight: "1px solid hsl(var(--border))",
  },
  ".cm-activeLine": { backgroundColor: TINT },
  ".cm-activeLineGutter": { backgroundColor: TINT },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "hsl(var(--foreground))" },
  [SELECTION_SELECTORS]: { backgroundColor: SELECTION },
});

/** Listed first: an earlier extension's theme wins, so the sheet overrides One Dark's surfaces. */
export function colourTheme(dark: boolean): Extension {
  return dark ? [sheetTheme, oneDark] : sheetTheme;
}

export function fontTheme(size: number): Extension {
  return EditorView.theme({
    "&": { fontSize: `${size}px` },
    ".cm-content": {
      fontFamily: '"JetBrains Mono Variable", ui-monospace, SFMono-Regular, Menlo, monospace',
    },
  });
}

export function editableExtension(editable: boolean, label: string): Extension {
  if (editable) {
    return EditorView.contentAttributes.of({ "aria-label": label });
  }
  return [
    EditorState.readOnly.of(true),
    EditorView.editable.of(false),
    EditorView.contentAttributes.of({ "aria-label": label, "aria-readonly": "true" }),
  ];
}

/** What can change after the view exists; the rest of the configuration is fixed at creation. */
export interface EditorCompartments {
  theme: Compartment;
  font: Compartment;
  wrap: Compartment;
  keys: Compartment;
  editable: Compartment;
  spell: Compartment;
}

export function createCompartments(): EditorCompartments {
  return {
    theme: new Compartment(),
    font: new Compartment(),
    wrap: new Compartment(),
    keys: new Compartment(),
    editable: new Compartment(),
    spell: new Compartment(),
  };
}

export interface ViewCallbacks {
  onChange?: (text: string) => void;
  onBlur?: () => void;
  onView?: (view: EditorView | null) => void;
}

export function wrapExtension(lineWrapping: boolean): Extension {
  return lineWrapping ? EditorView.lineWrapping : [];
}

/** The whole configuration of a new view, from the initial values of the live settings. */
export function editorExtensions(options: {
  compartments: EditorCompartments;
  callbacks: RefObject<ViewCallbacks>;
  collabExtension?: Extension;
  spellcheck?: Extension;
  settings: EditorSettings;
  dark: boolean;
  editable: boolean;
  label: string;
}): Extension[] {
  const {
    compartments: c,
    callbacks,
    collabExtension,
    spellcheck,
    settings,
    dark,
    editable,
    label,
  } = options;
  return [
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
    c.editable.of(editableExtension(editable, label)),
    c.keys.of(keymapExtension(settings.keymap)),
    c.font.of(fontTheme(settings.fontSize)),
    c.wrap.of(wrapExtension(settings.lineWrapping)),
    c.theme.of(colourTheme(dark)),
    c.spell.of(spellcheck ?? []),
  ];
}
