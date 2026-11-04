/**
 * Accepting and rejecting suggestions (spec 119 §5.4). Each decision is one Yjs transaction with the origin
 * `review-decision`, which no user's undo manager tracks: undoing your own typing never undoes someone's decision.
 */
import type * as Y from "yjs";

import { type Suggestion, type SuggestionMap, resolveSuggestion } from "./model";

export const REVIEW_ORIGIN = "review-decision";

export type Decision = "accept" | "reject" | "dismiss";

/**
 * Decides one suggestion. Accept and dismiss only drop the record (the text stays as it is). Reject undoes the
 * change: an insertion's text is removed, a deletion's text is put back. Returns false when the suggestion is
 * gone, or when a reject cannot find its place in the text.
 */
export function decideSuggestion(ytext: Y.Text, map: SuggestionMap, id: string, decision: Decision): boolean {
  const doc = ytext.doc;
  const fields = map.get(id);
  if (!doc || !fields) return false;
  const range = resolveSuggestion(ytext, fields);
  if (decision === "reject" && range === null) return false;
  doc.transact(() => applyDecision(ytext, map, { ...fields, id }, range, decision), REVIEW_ORIGIN);
  return true;
}

/** Decides every suggestion of the document in one transaction, as Accept all or Reject all. */
export function decideAllSuggestions(
  ytext: Y.Text,
  map: SuggestionMap,
  decision: "accept" | "reject",
): number {
  const doc = ytext.doc;
  if (!doc) return 0;
  const ids = Array.from(map.keys());
  let decided = 0;
  doc.transact(() => {
    for (const id of ids) {
      const fields = map.get(id);
      if (!fields) continue;
      // Each place is resolved when its turn comes: an earlier reject may have moved the text.
      const range = resolveSuggestion(ytext, fields);
      if (decision === "reject" && range === null) continue;
      applyDecision(ytext, map, { ...fields, id }, range, decision);
      decided += 1;
    }
  }, REVIEW_ORIGIN);
  return decided;
}

function applyDecision(
  ytext: Y.Text,
  map: SuggestionMap,
  suggestion: Suggestion,
  range: { from: number; to: number } | null,
  decision: Decision,
): void {
  if (decision === "reject" && range !== null) {
    if (suggestion.kind === "insert") {
      if (range.to > range.from) ytext.delete(range.from, range.to - range.from);
    } else {
      ytext.insert(range.from, suggestion.text);
    }
  }
  map.delete(suggestion.id);
}
