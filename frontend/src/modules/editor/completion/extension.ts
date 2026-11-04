import {
  type CompletionSource,
  acceptCompletion,
  autocompletion,
  completionKeymap,
} from "@codemirror/autocomplete";
import { Prec, type Extension } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { getCM } from "@replit/codemirror-vim";
import type { RefObject } from "react";

import { ignoredAt } from "./context";
import { RecentUses } from "./option";
import { bibSource } from "./sources/bib";
import { commandSource } from "./sources/commands";
import { environmentSource } from "./sources/environments";
import { bibResourceSource, bibliographySource, graphicsSource, inputSource } from "./sources/files";
import { labelSource } from "./sources/refs";
import { packageSource } from "./sources/packages";
import type { CompletionData, SourceEnv } from "./types";

const SOURCES = [
  commandSource,
  environmentSource,
  bibSource,
  labelSource,
  inputSource,
  graphicsSource,
  bibliographySource,
  bibResourceSource,
  packageSource,
];

/** A source that stays silent in comments and verbatim environments (spec 112). */
export function guarded(source: CompletionSource): CompletionSource {
  return (context) => (ignoredAt(context) ? null : source(context));
}

/**
 * Enter and Tab accept a completion only in insert mode. With the Vim keymap, normal mode keeps Enter for its own
 * motions; without Vim there is no mode and `getCM` returns null.
 */
function acceptInInsertMode(view: EditorView): boolean {
  const vim = getCM(view)?.state.vim;
  if (vim && !vim.insertMode) return false;
  return acceptCompletion(view);
}

const completionKeys = Prec.highest(
  keymap.of([
    ...completionKeymap.filter((binding) => binding.key !== "Enter"),
    { key: "Enter", run: acceptInInsertMode },
    { key: "Tab", run: acceptInInsertMode },
  ]),
);

/**
 * The completion of spec 112: the popup and its nine sources, one per trigger. Off, it is nothing at all, so the
 * editor is exactly what it was. `data` is read when a source runs, so it is never stale.
 */
export function autocompleteExtension(enabled: boolean, data: RefObject<CompletionData>): Extension {
  if (!enabled) return [];
  const env: SourceEnv = { data, recent: new RecentUses() };
  return [
    autocompletion({
      override: SOURCES.map((make) => guarded(make(env))),
      defaultKeymap: false,
      closeOnBlur: true,
    }),
    completionKeys,
  ];
}

/**
 * The popup in the sheet's own tokens (spec 106), so it reads the same in light and dark. Listed with the sheet
 * theme, so it wins over One Dark's tooltip colours.
 */
export const completionTheme = EditorView.theme({
  ".cm-tooltip.cm-tooltip-autocomplete": {
    backgroundColor: "hsl(var(--popover))",
    color: "hsl(var(--popover-foreground))",
    border: "1px solid hsl(var(--border))",
    borderRadius: "6px",
  },
  ".cm-tooltip-autocomplete ul li[aria-selected]": {
    backgroundColor: "hsl(var(--accent))",
    color: "hsl(var(--accent-foreground))",
  },
  ".cm-completionDetail": { color: "hsl(var(--muted-foreground))", fontStyle: "normal" },
  ".cm-completionInfo": { color: "hsl(var(--muted-foreground))" },
});
