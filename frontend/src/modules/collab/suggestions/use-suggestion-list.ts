/**
 * The suggestions of the open document as rows for the Suggestions tab (spec 119 §3), in text order. The list
 * follows the text and the map, and keeps its last value when nothing a row shows has changed, so typing
 * without suggestions does not re-render the editor's screen.
 */
import { useEffect, useState } from "react";
import type * as Y from "yjs";

import { type SuggestionMap, readSuggestions, suggestionsOf } from "./model";

export interface SuggestionListItem {
  id: string;
  kind: "insert" | "delete";
  authorName: string;
  createdAt: string;
  /** The inserted text, or the deleted text. */
  text: string;
  /** True when the place of the suggestion is gone: it can only be dismissed. */
  stale: boolean;
}

const NO_ROWS: SuggestionListItem[] = [];

/** The rows of the document now. Exported for the tests. */
export function suggestionRows(ytext: Y.Text, map: SuggestionMap): SuggestionListItem[] {
  const content = ytext.toString();
  return readSuggestions(ytext, map).map(({ suggestion, range }) => {
    const text =
      suggestion.kind === "delete" ? suggestion.text : range ? content.slice(range.from, range.to) : "";
    return {
      id: suggestion.id,
      kind: suggestion.kind === "insert" ? "insert" : "delete",
      authorName: suggestion.author_name,
      createdAt: suggestion.created_at,
      text,
      stale: range === null,
    };
  });
}

export function useSuggestionList(ytext: Y.Text | null): SuggestionListItem[] {
  const [rows, setRows] = useState<SuggestionListItem[]>(NO_ROWS);
  useEffect(() => {
    const map = ytext ? suggestionsOf(ytext) : null;
    if (!ytext || !map) {
      setRows(NO_ROWS);
      return undefined;
    }
    let last = "";
    const refresh = () => {
      const next = suggestionRows(ytext, map);
      const serialized = JSON.stringify(next);
      if (serialized === last) return;
      last = serialized;
      setRows(next);
    };
    refresh();
    ytext.observe(refresh);
    map.observe(refresh);
    return () => {
      ytext.unobserve(refresh);
      map.unobserve(refresh);
    };
  }, [ytext]);
  return rows;
}
