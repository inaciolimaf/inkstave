/**
 * What a suggestion looks like in the text (spec 119 §3): an insertion is underlined in its author's colour; a
 * deletion is a small struck-through widget with the removed text, folded to a word count when it is long and
 * unfolded on hover or focus. The look follows the inline review of spec 110 (the error and success tokens).
 */
import { type DecorationSet, Decoration, EditorView, WidgetType } from "@codemirror/view";

import i18n from "@/i18n/config";

import { colorForUser } from "../colors";
import { type PlacedSuggestion, SUGGESTION_FOLD_CHARS } from "./model";

/** The text of a deletion as the widget shows it: all of it, or a word count while folded. */
export function foldedLabel(text: string): string | null {
  if (text.length <= SUGGESTION_FOLD_CHARS) return null;
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return i18n.t("deleted.folded", { ns: "suggest", count: words });
}

export class DeletionWidget extends WidgetType {
  constructor(
    private readonly id: string,
    private readonly text: string,
    private readonly authorName: string,
  ) {
    super();
  }

  eq(other: DeletionWidget): boolean {
    return other.id === this.id && other.text === this.text && other.authorName === this.authorName;
  }

  toDOM(): HTMLElement {
    const folded = foldedLabel(this.text);
    const mark = document.createElement("span");
    mark.className = folded === null ? "cm-suggest-delete" : "cm-suggest-delete cm-suggest-delete-folded";
    mark.tabIndex = 0;
    mark.dataset.suggestionId = this.id;
    mark.setAttribute(
      "aria-label",
      i18n.t("deleted.label", { ns: "suggest", name: this.authorName, text: this.text }),
    );
    if (folded !== null) {
      const short = document.createElement("span");
      short.className = "cm-suggest-delete-short";
      short.textContent = folded;
      mark.append(short);
    }
    const full = document.createElement("span");
    full.className = "cm-suggest-delete-full";
    full.textContent = this.text;
    mark.append(full);
    return mark;
  }

  ignoreEvent(): boolean {
    return false;
  }
}

/** The insertion's underline, in the colour of its author; the decoration is an attribute, not a new text. */
function insertionMark(id: string, authorId: string): Decoration {
  return Decoration.mark({
    class: "cm-suggest-insert",
    attributes: {
      "data-suggestion-id": id,
      style: `text-decoration-color: ${colorForUser(authorId)}`,
    },
  });
}

/** The decorations of every placed suggestion, clamped to the text the view holds. */
export function suggestionDecorations(placed: PlacedSuggestion[], length: number): DecorationSet {
  const ranges = [];
  for (const { suggestion, range } of placed) {
    if (range === null) continue;
    if (suggestion.kind === "insert") {
      const from = Math.min(range.from, length);
      const to = Math.min(range.to, length);
      if (to > from) ranges.push(insertionMark(suggestion.id, suggestion.author_id).range(from, to));
    } else if (range.from <= length) {
      const widget = new DeletionWidget(suggestion.id, suggestion.text, suggestion.author_name);
      ranges.push(Decoration.widget({ widget, side: 1 }).range(range.from));
    }
  }
  return Decoration.set(ranges, true);
}

export const suggestionTheme = EditorView.baseTheme({
  ".cm-suggest-insert": {
    textDecoration: "underline",
    textDecorationThickness: "2px",
    textUnderlineOffset: "3px",
  },
  ".cm-suggest-delete": {
    textDecoration: "line-through",
    backgroundColor: "hsl(var(--error-soft))",
    color: "hsl(var(--error-text))",
    borderRadius: "2px",
    padding: "0 2px",
    cursor: "default",
  },
  ".cm-suggest-delete-folded .cm-suggest-delete-full": { display: "none" },
  ".cm-suggest-delete-short": { textDecoration: "none", display: "inline", fontStyle: "italic" },
  ".cm-suggest-delete-folded:hover .cm-suggest-delete-full, .cm-suggest-delete-folded:focus .cm-suggest-delete-full":
    { display: "inline" },
  ".cm-suggest-delete-folded:hover .cm-suggest-delete-short, .cm-suggest-delete-folded:focus .cm-suggest-delete-short":
    { display: "none" },
  ".cm-suggest-delete:focus-visible": { outline: "2px solid hsl(var(--ring))", outlineOffset: "1px" },
});
