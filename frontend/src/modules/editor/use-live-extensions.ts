import type { EditorView } from "@codemirror/view";
import { useEffect, type RefObject } from "react";

import {
  colourTheme,
  editableExtension,
  fontTheme,
  wrapExtension,
  type EditorCompartments,
} from "./codemirror-extensions";
import { keymapExtension } from "./keymap-extension";
import type { EditorSettings } from "./types";

/** Follows prop changes through the compartments, so the view is never recreated. */
export function useLiveExtensions(
  viewRef: RefObject<EditorView | null>,
  c: EditorCompartments,
  {
    settings,
    dark,
    editable,
    label,
  }: { settings: EditorSettings; dark: boolean; editable: boolean; label: string },
) {
  useEffect(() => {
    viewRef.current?.dispatch({ effects: c.editable.reconfigure(editableExtension(editable, label)) });
  }, [viewRef, c, editable, label]);

  useEffect(() => {
    viewRef.current?.dispatch({ effects: c.font.reconfigure(fontTheme(settings.fontSize)) });
  }, [viewRef, c, settings.fontSize]);

  useEffect(() => {
    viewRef.current?.dispatch({ effects: c.keys.reconfigure(keymapExtension(settings.keymap)) });
  }, [viewRef, c, settings.keymap]);

  useEffect(() => {
    viewRef.current?.dispatch({ effects: c.wrap.reconfigure(wrapExtension(settings.lineWrapping)) });
  }, [viewRef, c, settings.lineWrapping]);

  useEffect(() => {
    viewRef.current?.dispatch({ effects: c.theme.reconfigure(colourTheme(dark)) });
  }, [viewRef, c, dark]);
}
