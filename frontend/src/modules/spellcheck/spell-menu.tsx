import type { EditorView } from "@codemirror/view";
import { PopoverAnchor } from "@radix-ui/react-popover";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent } from "@/components/ui/popover";

import type { MisspelledWord } from "./spellcheck-extension";
import type { SpellcheckBinding } from "./types";

export interface SpellMenuState extends MisspelledWord {
  x: number;
  y: number;
}

/** Suggestions for one word, or null while they are being asked for. */
function useSuggestions(binding: SpellcheckBinding, word: string): string[] | null {
  const [items, setItems] = useState<string[] | null>(null);
  useEffect(() => {
    let live = true;
    setItems(null);
    binding.checker.suggest(binding.language, word).then(
      (result) => {
        if (live) setItems(result);
      },
      () => {
        if (live) setItems([]);
      },
    );
    return () => {
      live = false;
    };
  }, [binding.checker, binding.language, word]);
  return items;
}

/** Replaces the misspelled word, if the text under it is still the word the menu was opened for. */
function replaceWord(view: EditorView | null, hit: MisspelledWord, replacement: string): void {
  if (!view || view.state.sliceDoc(hit.from, hit.to) !== hit.word) return;
  view.dispatch({
    changes: { from: hit.from, to: hit.to, insert: replacement },
    selection: { anchor: hit.from + replacement.length },
  });
  view.focus();
}

/**
 * The menu of a misspelled word, opened by a right click (or a long press): up to five suggestions, then
 * "Add to dictionary" and "Ignore in this document". It is a Radix popover anchored at the pointer, because
 * a Radix context-menu trigger would suppress the native menu for every other word too.
 */
export function SpellMenu({
  state,
  view,
  binding,
  onClose,
}: {
  state: SpellMenuState;
  view: EditorView | null;
  binding: SpellcheckBinding;
  onClose: () => void;
}) {
  const { t } = useTranslation("editor");
  const suggestions = useSuggestions(binding, state.word);
  const done = (action: () => void) => () => {
    action();
    onClose();
  };

  return (
    <Popover open onOpenChange={(open) => !open && onClose()}>
      <PopoverAnchor asChild>
        <span aria-hidden="true" className="fixed size-0" style={{ left: state.x, top: state.y }} />
      </PopoverAnchor>
      <PopoverContent
        role="menu"
        aria-label={t("spellcheck.menuLabel")}
        align="start"
        className="w-60 p-1"
        onCloseAutoFocus={(event) => event.preventDefault()}
      >
        {suggestions === null && (
          <p className="px-2 py-1.5 text-small text-muted-foreground">{t("spellcheck.loading")}</p>
        )}
        {suggestions?.length === 0 && (
          <p className="px-2 py-1.5 text-small text-muted-foreground">{t("spellcheck.noSuggestions")}</p>
        )}
        {suggestions?.map((suggestion) => (
          <Button
            key={suggestion}
            role="menuitem"
            variant="ghost"
            size="sm"
            className="w-full justify-start font-medium"
            onClick={done(() => replaceWord(view, state, suggestion))}
          >
            {suggestion}
          </Button>
        ))}
        <div role="separator" className="my-1 h-px bg-border" />
        <Button
          role="menuitem"
          variant="ghost"
          size="sm"
          className="w-full justify-start"
          onClick={done(() => binding.addToDictionary(state.word))}
        >
          {t("spellcheck.addToDictionary")}
        </Button>
        <Button
          role="menuitem"
          variant="ghost"
          size="sm"
          className="w-full justify-start"
          onClick={done(() => binding.ignoreInDocument(state.word))}
        >
          {t("spellcheck.ignoreInDocument")}
        </Button>
      </PopoverContent>
    </Popover>
  );
}
