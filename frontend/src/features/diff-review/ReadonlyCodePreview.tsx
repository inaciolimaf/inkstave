/** A read-only CodeMirror 6 preview of would-be file content (spec 47, #192). */
import { EditorState } from "@codemirror/state";
import { EditorView, lineNumbers } from "@codemirror/view";
import { useEffect, useRef } from "react";

/**
 * A read-only CodeMirror 6 preview of the would-be file content (#192). Mounts a
 * single non-editable `EditorView` and full-replaces its document when `value`
 * changes. Reuses only `@codemirror/state` + `@codemirror/view` (no editor-feature
 * imports) so this surface stays self-contained.
 */
export function ReadonlyCodePreview({ value }: { value: string }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);

  useEffect(() => {
    if (!hostRef.current) return;
    const view = new EditorView({
      parent: hostRef.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          lineNumbers(),
          EditorView.lineWrapping,
          EditorState.readOnly.of(true),
          EditorView.editable.of(false),
        ],
      }),
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // Mount once; document updates are handled by the dispatch effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const view = viewRef.current;
    if (!view || view.state.doc.toString() === value) return;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } });
  }, [value]);

  return (
    <div
      ref={hostRef}
      data-testid="preview-editor"
      aria-label="File preview"
      aria-readonly="true"
      className="max-h-72 overflow-auto rounded-md border bg-muted/30 text-xs [&_.cm-editor]:bg-transparent"
    />
  );
}
