/**
 * Finds the words of LaTeX source that spell checking should look at (spec 113).
 *
 * A single pass over the whole text keeps the state right: a `$` opened before the visible range still
 * tells us the range is math. The skip rules are: comments, math (`$…$`, `$$…$$`, `\(…\)`, `\[…\]` and
 * math environments), verbatim-like environments and `\verb`, command names, optional `[…]` arguments,
 * the mandatory arguments of commands that hold keys, paths or code, words with digits, contractions and
 * elisions (`don't`, `d'água`), all-caps words of up to five letters, and words of one letter.
 */
import type { CheckableWord } from "./types";

/** Commands whose leading mandatory arguments hold keys, paths or code, with how many of them to skip. */
const SKIPPED_ARGUMENTS = new Map<string, number>([
  ["documentclass", 1],
  ["usepackage", 1],
  ["RequirePackage", 1],
  ["input", 1],
  ["include", 1],
  ["includeonly", 1],
  ["includegraphics", 1],
  ["label", 1],
  ["ref", 1],
  ["eqref", 1],
  ["pageref", 1],
  ["autoref", 1],
  ["cref", 1],
  ["Cref", 1],
  ["vref", 1],
  ["cite", 1],
  ["citep", 1],
  ["citet", 1],
  ["parencite", 1],
  ["textcite", 1],
  ["autocite", 1],
  ["nocite", 1],
  ["bibliography", 1],
  ["bibliographystyle", 1],
  ["bibitem", 1],
  ["url", 1],
  ["href", 1],
  ["end", 1],
  ["newcommand", 1],
  ["renewcommand", 1],
  ["setlength", 1],
  ["setcounter", 2],
  ["multicolumn", 2],
]);

/** Environments whose column specification is a mandatory argument, with how many to skip. */
const TABLE_ARGUMENTS = new Map<string, number>([
  ["tabular", 1],
  ["tabular*", 2],
  ["tabularx", 2],
  ["tabulary", 2],
  ["longtable", 1],
  ["array", 1],
  ["multicols", 1],
]);

const VERBATIM_ENVIRONMENTS = new Set([
  "verbatim",
  "verbatim*",
  "Verbatim",
  "Verbatim*",
  "lstlisting",
  "minted",
  "alltt",
  "comment",
  "filecontents",
  "filecontents*",
]);

const MATH_ENVIRONMENTS = new Set([
  "equation",
  "equation*",
  "align",
  "align*",
  "alignat",
  "alignat*",
  "flalign",
  "flalign*",
  "gather",
  "gather*",
  "multline",
  "multline*",
  "eqnarray",
  "eqnarray*",
  "displaymath",
  "math",
  "split",
  "aligned",
  "gathered",
  "cases",
]);

const WORD = /[\p{L}\p{M}\p{N}]+(?:['’][\p{L}\p{M}\p{N}]+)*/uy;
const COMMAND_NAME = /[a-zA-Z]+/y;
const ALL_CAPS = /^\p{Lu}{1,5}$/u;
const HAS_DIGIT_OR_APOSTROPHE = /[\p{N}'’]/u;
const MIN_WORD_LENGTH = 2;

/** The words of `text` that overlap `[from, to)`, with their offsets in `text`. */
export function checkableWords(text: string, from: number, to: number): CheckableWord[] {
  return scanText(text).filter((word) => word.to > from && word.from < to);
}

function scanText(text: string): CheckableWord[] {
  const found: CheckableWord[] = [];
  let pos = 0;
  while (pos < text.length) pos = step(text, pos, found);
  return found;
}

/** Consumes one construct at `pos`, recording its checkable word, and returns the next position. */
function step(text: string, pos: number, found: CheckableWord[]): number {
  const ch = text[pos];
  if (ch === "%") return lineEnd(text, pos);
  if (ch === "$") return dollarMath(text, pos);
  if (ch === "\\") return control(text, pos);
  const word = matchAt(WORD, text, pos);
  if (word === null) return pos + 1;
  if (isCheckable(word)) found.push({ from: pos, to: pos + word.length, word });
  return pos + word.length;
}

function matchAt(pattern: RegExp, text: string, pos: number): string | null {
  pattern.lastIndex = pos;
  const match = pattern.exec(text);
  return match ? match[0] : null;
}

function isCheckable(word: string): boolean {
  if (word.length < MIN_WORD_LENGTH) return false;
  if (HAS_DIGIT_OR_APOSTROPHE.test(word)) return false;
  return !ALL_CAPS.test(word);
}

/** Position just after the first `needle` at or after `from`; the end of the text when there is none. */
function indexAfter(text: string, needle: string, from: number): number {
  const at = text.indexOf(needle, from);
  return at < 0 ? text.length : at + needle.length;
}

function lineEnd(text: string, pos: number): number {
  return indexAfter(text, "\n", pos);
}

/** `$…$` and `$$…$$`. An unclosed `$` ends at a blank line, so one typo cannot hide the rest of the file. */
function dollarMath(text: string, pos: number): number {
  if (text[pos + 1] === "$") return indexAfter(text, "$$", pos + 2);
  for (let i = pos + 1; i < text.length; i++) {
    const ch = text[i];
    if (ch === "\\") i++;
    else if (ch === "$") return i + 1;
    else if (ch === "\n" && text[i + 1] === "\n") return i;
  }
  return text.length;
}

/** Matches the group that opens at `start`; -1 when it is not a group or does not close in the paragraph. */
function matchGroup(text: string, start: number, open: string, close: string): number {
  if (text[start] !== open) return -1;
  let depth = 0;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (ch === "\\") i++;
    else if (ch === open) depth++;
    else if (ch === close && --depth === 0) return i + 1;
    else if (ch === "\n" && text[i + 1] === "\n") return -1;
  }
  return -1;
}

/** Skips optional `[…]` arguments and then `count` mandatory `{…}` arguments that follow `pos` directly. */
function skipArguments(text: string, pos: number, count: number): number {
  let next = pos;
  for (let end = matchGroup(text, next, "[", "]"); end >= 0; end = matchGroup(text, next, "[", "]")) {
    next = end;
  }
  for (let i = 0; i < count; i++) {
    const end = matchGroup(text, next, "{", "}");
    if (end < 0) break;
    next = end;
  }
  return next;
}

function control(text: string, pos: number): number {
  const next = text[pos + 1];
  if (next === undefined) return pos + 1;
  if (!/[a-zA-Z]/.test(next)) return controlSymbol(text, pos, next);
  const name = matchAt(COMMAND_NAME, text, pos + 1) ?? "";
  const after = pos + 1 + name.length;
  if (name === "begin") return environment(text, after);
  if (name === "verb") return inlineVerbatim(text, after);
  return skipArguments(text, after, SKIPPED_ARGUMENTS.get(name) ?? 0);
}

/** `\(`, `\[` are math; any other symbol (`\%`, `\\`, `\$`) is a single character and is not checked. */
function controlSymbol(text: string, pos: number, next: string): number {
  if (next === "(") return indexAfter(text, "\\)", pos + 2);
  if (next === "[") return indexAfter(text, "\\]", pos + 2);
  return pos + 2;
}

function environment(text: string, after: number): number {
  const end = matchGroup(text, after, "{", "}");
  if (end < 0) return after;
  const name = text.slice(after + 1, end - 1);
  if (VERBATIM_ENVIRONMENTS.has(name) || MATH_ENVIRONMENTS.has(name)) {
    return indexAfter(text, `\\end{${name}}`, end);
  }
  return skipArguments(text, end, TABLE_ARGUMENTS.get(name) ?? 0);
}

/** `\verb|…|` and `\verb*|…|`, which stay on one line. */
function inlineVerbatim(text: string, after: number): number {
  const start = text[after] === "*" ? after + 1 : after;
  const delimiter = text[start];
  if (delimiter === undefined || delimiter === "\n") return start;
  const close = text.indexOf(delimiter, start + 1);
  const lineBreak = text.indexOf("\n", start + 1);
  if (close < 0 || (lineBreak >= 0 && lineBreak < close)) return start;
  return close + 1;
}
