/**
 * CodeMirror 6 inline diagnostics from compile problems (spec 27).
 *
 * Problems for the **currently open file** are mapped to `@codemirror/lint`
 * diagnostics and pushed imperatively (`setDiagnostics`), so they refresh on each
 * compile and are replaced wholesale rather than recomputed on every keystroke.
 */
import { type Diagnostic, lintGutter, setDiagnostics } from "@codemirror/lint";
import type { Text } from "@codemirror/state";
import type { EditorView } from "@codemirror/view";

import type { Problem, ProblemSeverity } from "@/features/pdf-preview/problems";

const SEVERITY_MAP: Record<ProblemSeverity, Diagnostic["severity"]> = {
  error: "error",
  warning: "warning",
  info: "info",
};

/** Gutter markers for diagnostics; add to the editor's extensions. */
export const lintGutterExtension = lintGutter();

/** Map problems (already filtered to the open file) to CM diagnostics. */
export function problemsToDiagnostics(doc: Text, problems: Problem[]): Diagnostic[] {
  const out: Diagnostic[] = [];
  for (const problem of problems) {
    if (problem.line == null) continue;
    const startLine = Math.max(1, Math.min(problem.line, doc.lines));
    const endLine =
      problem.end_line != null
        ? Math.max(startLine, Math.min(problem.end_line, doc.lines))
        : startLine;
    out.push({
      from: doc.line(startLine).from,
      to: doc.line(endLine).to,
      severity: SEVERITY_MAP[problem.severity],
      message: problem.message,
      source: problem.rule,
    });
  }
  return out;
}

/** Replace the editor's diagnostics with those for the given problems. */
export function applyDiagnostics(view: EditorView, problems: Problem[]): void {
  view.dispatch(setDiagnostics(view.state, problemsToDiagnostics(view.state.doc, problems)));
}
