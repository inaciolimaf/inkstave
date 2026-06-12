/** Strings for the PDF preview / compile feature (the `preview` namespace). */
const dict = {
  compile: {
    compile: "Compile",
    compiling: "Compiling…",
    queued: "Queued…",
    working: "Working…",
    compileProject: "Compile project",
    cancelCompilation: "Cancel compilation",
    progressLabel: "Compiling",
  },
  announce: {
    succeeded: "Compilation succeeded.",
    failed: "Compilation failed.",
    timedOut: "Compilation timed out.",
    cancelled: "Compilation cancelled.",
    error: "Compilation error.",
  },
  status: {
    exit: "exit {{code}}",
  },
  errorState: {
    failureTitle: "Compilation failed",
    failureMessage: "Your document didn’t compile. Check the log for the LaTeX errors.",
    timeoutTitle: "Compilation timed out",
    timeoutMessage:
      "The compile took too long and was stopped. Simplify the document or try again.",
    errorTitle: "Something went wrong",
    errorMessage: "The compile couldn’t be completed due to a system error.",
    viewLog: "View log",
    tryAgain: "Try again",
  },
  empty: {
    noPreview: "No preview yet",
    compileToPreview: "Compile to see a preview of your document.",
  },
  loading: {
    loadingPdfLabel: "Loading PDF",
    loadingPreview: "Loading preview…",
    pdfErrorLabel: "PDF error",
  },
  pane: {
    label: "PDF preview pane",
    compileOutput: "Compile output",
    pdfPreview: "PDF preview",
  },
  log: {
    title: "Log",
    copyToClipboard: "Copy log to clipboard",
    compileLog: "Compile log",
    loadingLog: "Loading log…",
    noLogOutput: "No log output.",
  },
  problems: {
    title: "Problems",
    region: "Compile problems",
    noLogYet: "No log yet — run a compile.",
    noProblems: "No problems.",
    updating: "updating…",
    loading: "loading…",
    errors: "Errors",
    warnings: "Warnings",
    typesetting: "Typesetting",
    group: "{{label}} ({{count}})",
    countSeverity: "{{count}} {{severity}}",
    rowLabel: "{{severity}}: {{message}}{{location}}",
  },
  toolbar: {
    zoomOut: "Zoom out",
    zoomIn: "Zoom in",
    zoomLevel: "Zoom level",
    fitWidth: "Fit width",
    fitPage: "Fit page",
    previousPage: "Previous page",
    nextPage: "Next page",
    pageNumber: "Page number",
    of: "of {{numPages}}",
    downloadPdf: "Download PDF",
  },
  viewer: {
    page: "Page {{pageNumber}}",
  },
  errors: {
    startCompile: "Could not start the compile.",
    loadLog: "Could not load the log.",
    loadPdf: "Could not load the PDF.",
  },
  sync: {
    unavailable: "SyncTeX data not available for this compile",
    noMatch: "No matching location",
    failed: "Sync failed",
  },
};

export default dict;
export type Dict = typeof dict;
