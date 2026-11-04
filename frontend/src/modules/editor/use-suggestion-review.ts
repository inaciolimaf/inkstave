/**
 * The Suggestions tab's data and actions for the open document (spec 119 §3, §5.4): its rows, and Accept or
 * Reject through the CRDT. A viewer gets the rows without the actions. Dismiss drops a record whose place is gone.
 */
import type * as Y from "yjs";

import {
  type Decision,
  decideAllSuggestions,
  decideSuggestion,
  suggestionsOf,
  useSuggestionList,
} from "@/modules/collab";
import type { SuggestionDecision, SuggestionsTabProps } from "@/modules/discussion";
import { isReadOnly, usePermissions } from "@/modules/sharing";

function toDecision(decision: SuggestionDecision): Decision {
  return decision === "reject" ? "reject" : "accept";
}

export function useSuggestionReview(projectId: string, text: Y.Text | null): SuggestionsTabProps {
  const rows = useSuggestionList(text);
  const canDecide = !isReadOnly(usePermissions(projectId).data);
  const map = text ? suggestionsOf(text) : null;
  return {
    rows,
    canDecide,
    onDecide: (id, decision) => {
      if (text && map) decideSuggestion(text, map, id, toDecision(decision));
    },
    onDecideAll: (decision) => {
      if (text && map) decideAllSuggestions(text, map, decision);
    },
  };
}
