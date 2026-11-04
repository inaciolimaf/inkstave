import type { CompletionContext } from "@codemirror/autocomplete";

/** Environments whose body is not LaTeX: nothing inside them completes. */
const VERBATIM_BOUNDARY = /\\(begin|end)\{(verbatim\*?|lstlisting|minted|comment)\}/g;

/** What precedes the environment name; an environment snippet replaces from its backslash. */
export const BEGIN_PREFIX = "\\begin{";
/** What an argument may hold while its item is typed: no braces, no comma. */
export const ARGUMENT_PATTERN = /^[^{},]*$/;

/** The argument commands whose comma-separated list completes one item at a time (`\cite{a, b`). */
export const CITE_COMMANDS = ["cite", "citep", "citet", "parencite", "textcite", "autocite", "nocite"];
export const REF_COMMANDS = ["ref", "eqref", "autoref", "cref", "Cref", "pageref", "nameref"];
export const INPUT_COMMANDS = ["input", "include", "subfile"];
export const GRAPHICS_COMMANDS = ["includegraphics"];
export const PACKAGE_COMMANDS = ["usepackage", "RequirePackage"];

/** A completion's typed prefix: where it starts in the document and the text typed so far. */
export interface Token {
  from: number;
  text: string;
}

/** True when an unescaped `%` starts a comment somewhere in the text before the cursor on its line. */
export function inComment(lineBefore: string): boolean {
  for (let i = 0; i < lineBefore.length; i++) {
    if (lineBefore[i] === "\\") i++;
    else if (lineBefore[i] === "%") return true;
  }
  return false;
}

/** True when the text before the cursor is inside a verbatim-like environment. */
export function inVerbatim(before: string): boolean {
  let open: string | null = null;
  for (const match of before.matchAll(VERBATIM_BOUNDARY)) {
    if (open === null && match[1] === "begin") open = match[2];
    else if (match[1] === "end" && match[2] === open) open = null;
  }
  return open !== null;
}

/** True when completion must stay silent at the cursor: in a comment or in a verbatim environment. */
export function ignoredAt(context: CompletionContext): boolean {
  const line = context.state.doc.lineAt(context.pos);
  if (inComment(line.text.slice(0, context.pos - line.from))) return true;
  return inVerbatim(context.state.sliceDoc(0, context.pos));
}

/** A `\` followed by letters before the cursor. */
export function commandToken(context: CompletionContext): Token | null {
  const match = context.matchBefore(/\\[A-Za-z]*/);
  return match ? { from: match.from, text: match.text } : null;
}

/** The name typed after `\begin{`. `from` is its first character, so the match filters on the name alone. */
export function environmentToken(context: CompletionContext): Token | null {
  const match = context.matchBefore(/\\begin\{[\w*-]*/);
  if (!match) return null;
  const from = match.from + BEGIN_PREFIX.length;
  return { from, text: context.state.sliceDoc(from, context.pos) };
}

/**
 * The item being typed inside one of `commands`' braces. After a comma the item starts again, so
 * `\cite{a, b` completes `b`. Optional arguments (`\cite[p.~5]{`) are skipped.
 */
export function argumentToken(context: CompletionContext, commands: readonly string[]): Token | null {
  const names = commands.join("|");
  const match = context.matchBefore(new RegExp(String.raw`\\(?:${names})(?:\[[^\]\n]*\])?\{[^{}\n]*`));
  if (!match) return null;
  const brace = match.text.lastIndexOf("{");
  const list = match.text.slice(brace + 1);
  const item = list.slice(list.lastIndexOf(",") + 1);
  const from = match.from + brace + 1 + (list.length - item.length) + (item.length - item.trimStart().length);
  return { from, text: context.state.sliceDoc(from, context.pos) };
}
