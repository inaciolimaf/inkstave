import { defaultKeymap, historyKeymap } from "@codemirror/commands";
import type { Extension } from "@codemirror/state";
import { keymap } from "@codemirror/view";
import { emacs } from "@replit/codemirror-emacs";
import { vim } from "@replit/codemirror-vim";

import type { EditorKeymap } from "@/types";

/**
 * Map the user's keymap preference (spec 59) to CodeMirror extensions. The vim/
 * emacs handlers must precede the base keymap so they capture keys first.
 */
export function keymapExtension(km: EditorKeymap = "default"): Extension {
  const base = keymap.of([...defaultKeymap, ...historyKeymap]);
  if (km === "vim") return [vim(), base];
  if (km === "emacs") return [emacs(), base];
  return base;
}
