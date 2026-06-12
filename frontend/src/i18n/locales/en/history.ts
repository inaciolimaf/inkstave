/** Strings for the version-history panel (the `history` namespace, spec 38). */
const dict = {
  panel: {
    title: "Version history",
    description:
      "Browse versions, see what changed, and restore — restoring creates a new version.",
  },
  timeline: {
    ariaLabel: "Version history",
    empty: "No history yet.",
    loadFailed: "Couldn’t load history.",
    loadMore: "Load more",
    loading: "Loading…",
    unknownAuthor: "Unknown",
    changes_one: "{{count}} change",
    changes_other: "{{count}} changes",
  },
  diff: {
    ariaLabel: "Version diff",
    selectPrompt: "Select a version to see what changed.",
    loadFailed: "Couldn’t load the diff.",
    binary: "This document has no text diff.",
    tooLarge: "This version is too large to diff.",
    noChanges: "No changes between these versions.",
    labelsForVersion: "Labels for version {{version}}",
  },
  labels: {
    namePlaceholder: "Label name",
    nameAriaLabel: "Label name",
    add: "Add",
    addToVersion: "Add label to version {{version}}",
    remove: "Remove label {{name}}",
  },
  restore: {
    trigger: "Restore this version",
    confirmTitle: "Restore version {{version}}?",
    confirmDescription:
      "The document’s current content will be replaced with version {{version}}. A new version is created — nothing is deleted, and you can restore back at any time.",
    labelPlaceholder: "Add a label for this restore (optional)",
    labelAriaLabel: "Restore label",
    cancel: "Cancel",
    action: "Restore",
    restoring: "Restoring…",
    success: "Restored to version {{version}}; created version {{newVersion}}.",
    error: "Restore failed. Please try again.",
  },
  toast: {
    addLabelFailed: "Couldn’t add the label.",
    removeLabelFailed: "Couldn’t remove the label.",
  },
};

export default dict;
export type Dict = typeof dict;
