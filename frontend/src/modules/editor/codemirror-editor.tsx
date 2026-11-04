import { EditorState, type Extension } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  spellcheckFor,
  SpellMenu,
  type MisspelledWord,
  type SpellcheckBinding,
  type SpellMenuState,
} from "@/modules/spellcheck";

import { createCompartments, editorExtensions, type ViewCallbacks } from "./codemirror-extensions";
import type { EditorSettings } from "./types";
import { useLiveExtensions } from "./use-live-extensions";

export function CodeMirrorEditor({
  doc,
  settings,
  dark,
  editable = false,
  onChange,
  onBlur,
  onView,
  collabExtension,
  spellcheck = null,
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
  /** Spell check for this document; null while it is off (spec 113). */
  spellcheck?: SpellcheckBinding | null;
}) {
  const { t } = useTranslation("editor");
  const editorLabel = t("cm.label");
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const callbacks = useRef<ViewCallbacks>({ onChange, onBlur, onView });
  callbacks.current = { onChange, onBlur, onView };
  const labelRef = useRef(editorLabel);
  labelRef.current = editorLabel;
  const compartments = useRef(createCompartments());
  const [spellMenu, setSpellMenu] = useState<SpellMenuState | null>(null);
  const openSpellMenu = useCallback(
    (hit: MisspelledWord, pointer: { x: number; y: number }) => setSpellMenu({ ...hit, ...pointer }),
    [],
  );
  const appliedSpellcheck = useRef(spellcheck);

  // Create the view exactly once; later changes go through compartments/dispatch.
  useEffect(() => {
    const state = EditorState.create({
      // In collab mode the CRDT seeds the content; start empty.
      doc: collabExtension ? "" : doc,
      extensions: editorExtensions({
        compartments: compartments.current,
        callbacks,
        collabExtension,
        spellcheck: spellcheck ? spellcheckFor(spellcheck, openSpellMenu) : undefined,
        settings,
        dark,
        editable,
        label: labelRef.current,
      }),
    });
    const view = new EditorView({ state, parent: hostRef.current! });
    viewRef.current = view;
    callbacks.current.onView?.(view);
    return () => {
      callbacks.current.onView?.(null);
      view.destroy();
      viewRef.current = null;
    };
    // Every prop here is an initial value: later changes go through the compartments below, and
    // recreating the view would drop the undo history and the selection.
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
    // `collabExtension` is fixed for the life of the view, so only `doc` can trigger a swap.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc]);

  // Turning spell check on, off or changing its words reconfigures the view; the view is kept.
  useEffect(() => {
    if (appliedSpellcheck.current === spellcheck) return;
    appliedSpellcheck.current = spellcheck;
    const effect = spellcheck ? spellcheckFor(spellcheck, openSpellMenu) : [];
    viewRef.current?.dispatch({ effects: compartments.current.spell.reconfigure(effect) });
    setSpellMenu(null);
  }, [spellcheck, openSpellMenu]);

  useLiveExtensions(viewRef, compartments.current, { settings, dark, editable, label: editorLabel });

  return (
    <>
      <div ref={hostRef} className="h-full overflow-auto text-body" data-testid="cm-host" />
      {spellMenu && spellcheck && (
        <SpellMenu
          state={spellMenu}
          view={viewRef.current}
          binding={spellcheck}
          onClose={() => setSpellMenu(null)}
        />
      )}
    </>
  );
}
