/** Strings for the diff-review surface (the `review` namespace, spec 47). */
const dict = {
  title: "Review proposed changes",
  description:
    "Review the agent’s proposed changes and accept or reject each hunk before applying.",
  accepted: "{{accepted}}/{{total}} accepted",
  apply: "Apply",
  loadError: "Couldn’t load the proposal.",
  noChanges: "This proposal has no changes.",
  applyResult: {
    successTitle: "Changes applied",
    errorTitle: "Some changes could not be applied",
    applied: "{{count}} applied",
    skipped: ", {{count}} skipped",
    error: " — error: {{error}}",
  },
  toast: {
    applyError: "Some changes couldn’t be applied.",
    applySuccess: "Changes applied to your document.",
  },
  confirmApply: {
    title: "Apply changes?",
    // Variants keyed by the two plural axes: `applicable` (change/changes) and
    // `fileCount` (file/files + document/documents).
    description:
      "This will write {{applicable}} accepted change across {{fileCount}} file into your document.",
    description_fileMany:
      "This will write {{applicable}} accepted change across {{fileCount}} files into your documents.",
    descriptionMany:
      "This will write {{applicable}} accepted changes across {{fileCount}} file into your document.",
    descriptionMany_fileMany:
      "This will write {{applicable}} accepted changes across {{fileCount}} files into your documents.",
    blocked: " {{count}} hunk no longer apply and will be skipped.",
    blockedMany: " {{count}} hunks no longer apply and will be skipped.",
    confirm: "Apply",
  },
  confirmDiscard: {
    title: "Discard your review?",
    description: "Your accept/reject choices will be lost.",
    keep: "Keep reviewing",
    discard: "Discard",
  },
  file: {
    changesTo: "Changes to {{path}}",
    newFile: "New file",
    deleted: "Deleted",
    hunkCount: "{{accepted}}/{{total}} hunks",
    acceptAll: "Accept all",
    rejectAll: "Reject all",
    diff: "Diff",
    preview: "Preview",
    baseChangedTitle: "This file changed since the proposal",
    baseChangedDescription: "Hunks that no longer apply are marked and will be skipped.",
  },
  hunk: {
    noLongerApplies: "No longer applies",
    accept: "Accept",
    reject: "Reject",
    acceptChange: "Accept change: {{header}}",
    added: "added",
    removed: "removed",
  },
  filePreview: "File preview",
};

export default dict;
export type Dict = typeof dict;
