/**
 * A math region of a LaTeX text. `from` and `to` bound the body only: the delimiters around it are not part of
 * the range, so a replacement of the body keeps them (spec 114 §5.4).
 */
export interface MathRegion {
  from: number;
  to: number;
  latex: string;
  delimiters: { open: string; close: string };
}

interface Opener {
  open: string;
  close: string;
  bodyFrom: number;
}

const ENVIRONMENT = /\\begin\{((?:equation|align|gather|multline)\*?)\}/y;

function openerAt(text: string, i: number): Opener | null {
  if (text.startsWith("$$", i)) return { open: "$$", close: "$$", bodyFrom: i + 2 };
  if (text[i] === "$") return { open: "$", close: "$", bodyFrom: i + 1 };
  if (text.startsWith("\\(", i)) return { open: "\\(", close: "\\)", bodyFrom: i + 2 };
  if (text.startsWith("\\[", i)) return { open: "\\[", close: "\\]", bodyFrom: i + 2 };
  ENVIRONMENT.lastIndex = i;
  const match = ENVIRONMENT.exec(text);
  if (!match) return null;
  return { open: match[0], close: `\\end{${match[1]}}`, bodyFrom: i + match[0].length };
}

/** The next position to look at after a character that opens nothing: a comment or an escaped character. */
function skip(text: string, i: number): number {
  if (text[i] === "%") {
    const newline = text.indexOf("\n", i);
    return newline < 0 ? text.length : newline + 1;
  }
  return text[i] === "\\" ? i + 2 : i + 1;
}

/** Where the closing delimiter starts, or -1. An escaped character is never a delimiter. */
function findClose(text: string, from: number, close: string): number {
  let j = from;
  while (j < text.length) {
    if (text.startsWith(close, j)) return j;
    j = text[j] === "\\" ? j + 2 : j + 1;
  }
  return -1;
}

/** Every math region of the text, in order, none overlapping the next. */
export function findMath(text: string): MathRegion[] {
  const regions: MathRegion[] = [];
  let i = 0;
  while (i < text.length) {
    const opener = openerAt(text, i);
    if (!opener) {
      i = skip(text, i);
      continue;
    }
    const to = findClose(text, opener.bodyFrom, opener.close);
    if (to < 0) {
      i = opener.bodyFrom;
      continue;
    }
    const delimiters = { open: opener.open, close: opener.close };
    regions.push({ from: opener.bodyFrom, to, latex: text.slice(opener.bodyFrom, to), delimiters });
    i = to + opener.close.length;
  }
  return regions;
}

/** The math the offset is in, its body included. Null outside math. */
export function mathAt(text: string, offset: number): MathRegion | null {
  return findMath(text).find((region) => offset >= region.from && offset <= region.to) ?? null;
}

/** Math as new text: `\( … \)` inline, or an `equation` environment on lines of its own when displayed. */
export function wrapMath(latex: string, display: boolean): string {
  if (display) return `\\begin{equation}\n${latex}\n\\end{equation}`;
  return `\\(${latex}\\)`;
}
