/** Strings for the inline review of the agent's proposals, in the text (the `review` namespace, specs 47, 110). */
const dict = {
  /** The counter, the buttons, and the toolbar on each change. */
  bar: {
    label: "Review in the text",
    counter: "Change {{index}} of {{total}}",
    previous: "Previous",
    next: "Next",
    acceptAll: "Accept all",
    rejectAll: "Reject all",
    close: "Close",
  },
  inline: {
    counter: "Change {{index}} of {{total}}",
    accept: "Accept",
    reject: "Reject",
    acceptHunk: "Accept change {{index}}",
    rejectHunk: "Reject change {{index}}",
    blocked: "This part changed since the proposal",
  },
  toast: {
    acceptError: "The change couldn’t be written. Try again.",
    saveError: "The decision couldn’t be saved. Try again.",
    drifted: "This part changed since the proposal, so it can only be rejected.",
    alreadyDecided: "This proposal was already decided.",
    notInProject: "This file is not in the project.",
    loadError: "Couldn’t load the proposal.",
  },
};

export default dict;
export type Dict = typeof dict;
