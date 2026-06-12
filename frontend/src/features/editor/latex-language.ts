/**
 * A small, self-authored LaTeX highlighter built on CodeMirror's
 * `StreamLanguage` — highlights commands, comments and math. This is Inkstave's
 * own code (MIT); it deliberately does **not** use or translate Overleaf's
 * AGPL `lezer-latex` grammar. See docs/adr/0018-latex-language.md.
 */
import { LanguageSupport, StreamLanguage } from "@codemirror/language";

interface LatexState {
  math: boolean;
}

export const latexStreamLanguage = StreamLanguage.define<LatexState>({
  name: "latex",
  startState: () => ({ math: false }),
  token(stream, state) {
    // Comment to end of line.
    if (!state.math && stream.match(/%.*/)) return "comment";
    // Math toggles ($$ before $).
    if (stream.match("$$")) {
      state.math = !state.math;
      return "string";
    }
    if (stream.peek() === "$") {
      stream.next();
      state.math = !state.math;
      return "string";
    }
    if (state.math) {
      stream.next();
      return "string";
    }
    // Commands: \word (optionally starred) or an escaped symbol like \{ \% \\.
    if (stream.match(/\\[a-zA-Z@]+\*?/) || stream.match(/\\./)) return "keyword";
    if (stream.match(/[{}[\]]/)) return "bracket";
    stream.next();
    return null;
  },
});

export function latex(): LanguageSupport {
  return new LanguageSupport(latexStreamLanguage);
}
