/** Strings for suggested changes (Suggesting mode, spec 119): the switch, the marks in the text and the tab (the `suggest` namespace). */
const dict = {
  /** The switch in the editor's status line. */
  mode: {
    label: "Suggesting",
    hint: "Suggest changes: what you type and delete becomes a suggestion that others accept or reject.",
    on: "Suggesting on",
    off: "Suggesting off",
    failed: "Your Suggesting setting couldn’t be saved.",
  },
  /** Hover or focus on a suggestion in the text. */
  popover: {
    label: "Suggestion by {{name}}",
    insertion: "Suggested insertion",
    deletion: "Suggested deletion",
    accept: "Accept",
    reject: "Reject",
    dismiss: "Dismiss",
  },
  /** A suggested deletion in the text, folded when long. */
  deleted: {
    folded_one: "…{{count}} word",
    folded_other: "…{{count}} words",
    label: "Suggested deletion by {{name}}: {{text}}",
  },
  /** The notice when a deletion is too large to record as a suggestion. */
  blocked: "Too much to delete as a suggestion. Turn Suggesting off to delete it.",
  /** The presence mark on a member who is suggesting. */
  presence: {
    suggesting: "suggesting",
  },
  /** The Suggestions tab of the review column. */
  tab: {
    label: "Suggestions",
    empty: "No suggestions in this document.",
    insertion: "Insertion",
    deletion: "Deletion",
    by: "by {{name}}",
    stale: "No longer applies",
    acceptAll: "Accept all",
    rejectAll: "Reject all",
    accept: "Accept",
    reject: "Reject",
    dismiss: "Dismiss",
    rowLabel: "{{kind}} by {{name}}",
  },
};

export default dict;
export type Dict = typeof dict;
