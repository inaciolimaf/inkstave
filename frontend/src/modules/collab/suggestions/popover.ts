/**
 * The popover of a suggestion (spec 119 §3): hovering over an insertion or at a deletion shows its author, its
 * time and, for a member who can write, Accept and Reject.
 */
import { type Extension } from "@codemirror/state";
import { type Tooltip, hoverTooltip } from "@codemirror/view";
import type * as Y from "yjs";

import i18n from "@/i18n/config";
import { formatDateTime } from "@/lib/formatting";

import { type PlacedSuggestion, type SuggestionMap, readSuggestions } from "./model";
import { decideSuggestion } from "./review";

export interface PopoverOptions {
  ytext: Y.Text;
  suggestions: SuggestionMap;
  canDecide: boolean;
}

const BUTTON =
  "inline-flex min-h-8 items-center justify-center rounded border border-control-edge bg-background px-2 text-small font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

function popoverDom(options: PopoverOptions, placed: PlacedSuggestion): HTMLElement {
  const { suggestion } = placed;
  const root = document.createElement("div");
  root.className =
    "cm-suggest-popover space-y-2 rounded-md border border-border bg-popover p-3 text-small text-popover-foreground shadow-md";
  root.dataset.suggestionId = suggestion.id;
  const kind = i18n.t(suggestion.kind === "insert" ? "popover.insertion" : "popover.deletion", {
    ns: "suggest",
  });
  const head = document.createElement("p");
  head.className = "font-medium";
  head.textContent = `${kind}: ${suggestion.author_name}`;
  const when = document.createElement("p");
  when.className = "text-muted-foreground";
  when.textContent = formatDateTime(suggestion.created_at);
  root.append(head, when);
  if (options.canDecide) {
    const row = document.createElement("div");
    row.className = "flex gap-2";
    for (const decision of ["accept", "reject"] as const) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = BUTTON;
      button.textContent = i18n.t(decision === "accept" ? "popover.accept" : "popover.reject", {
        ns: "suggest",
      });
      button.addEventListener("click", () => {
        decideSuggestion(options.ytext, options.suggestions, suggestion.id, decision);
      });
      row.append(button);
    }
    root.append(row);
  }
  return root;
}

/** The suggestion under a position: an insertion it is inside, or a deletion it is at. */
function suggestionAt(options: PopoverOptions, pos: number): PlacedSuggestion | null {
  for (const placed of readSuggestions(options.ytext, options.suggestions)) {
    const range = placed.range;
    if (range === null) continue;
    const hit =
      placed.suggestion.kind === "insert"
        ? range.to > range.from && pos >= range.from && pos <= range.to
        : Math.abs(pos - range.from) <= 1;
    if (hit) return placed;
  }
  return null;
}

export function suggestPopover(options: PopoverOptions): Extension {
  return hoverTooltip(
    (_view, pos): Tooltip | null => {
      const placed = suggestionAt(options, pos);
      if (!placed || !placed.range) return null;
      const { range } = placed;
      return {
        pos: range.from,
        end: range.to,
        above: true,
        create: () => ({ dom: popoverDom(options, placed) }),
      };
    },
    { hoverTime: 350 },
  );
}
