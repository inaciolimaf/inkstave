/** What a replacement writes, as edits on the text (spec 122). Pure, no DOM. */
import type { TextMatch } from "./find";

/** One change to a text: `[from, to)` becomes `insert`. */
export interface TextEdit {
  from: number;
  to: number;
  insert: string;
}

/** `$$`, `$&`, `$1`…`$99` and `$<name>`, the references `String.prototype.replace` knows. */
const REFERENCE = /\$(\$|&|<([^>]*)>|(\d{1,2}))/g;

function groupReference(match: TextMatch, digits: string, whole: string): string {
  const two = Number(digits);
  if (two >= 1 && two <= match.groups.length) return match.groups[two - 1] ?? "";
  // `$12` with one group is `$1` followed by "2", as in JavaScript.
  const one = Number(digits[0]);
  if (digits.length === 2 && one >= 1 && one <= match.groups.length) {
    return (match.groups[one - 1] ?? "") + digits[1];
  }
  return whole;
}

/**
 * The text that replaces `match`. A plain search writes the replacement as typed, `$` included. A regular
 * expression expands its references; one that names no group stays as typed.
 */
export function expandReplacement(template: string, match: TextMatch, regex: boolean): string {
  if (!regex) return template;
  return template.replace(REFERENCE, (whole, token: string, name?: string, digits?: string) => {
    if (token === "$") return "$";
    if (token === "&") return match.text;
    if (name !== undefined) return name in match.named ? (match.named[name] ?? "") : whole;
    return groupReference(match, digits ?? "", whole);
  });
}

/** One edit per match, in text order. */
export function replacementEdits(
  matches: readonly TextMatch[],
  template: string,
  regex: boolean,
): TextEdit[] {
  return matches.map((match) => ({
    from: match.from,
    to: match.to,
    insert: expandReplacement(template, match, regex),
  }));
}

/** `text` with `edits` applied. The edits must not overlap; their order does not matter. */
export function applyEdits(text: string, edits: readonly TextEdit[]): string {
  const sorted = [...edits].sort((a, b) => a.from - b.from);
  let out = "";
  let at = 0;
  for (const edit of sorted) {
    out += text.slice(at, edit.from) + edit.insert;
    at = edit.to;
  }
  return out + text.slice(at);
}

function sameMatch(a: TextMatch, b: TextMatch): boolean {
  return a.text === b.text && a.lineText === b.lineText && a.column === b.column;
}

/**
 * The match in the current text that stands for `wanted`, found in an older copy whose matches were `seen`: the
 * same text at the same column of a line that reads the same. Among identical lines, the one with the same rank
 * wins while their number is unchanged, and the nearest one otherwise. `null` when no line reads the same, so a
 * replace never lands somewhere the writer did not see.
 */
export function relocate(
  current: readonly TextMatch[],
  wanted: TextMatch,
  seen: readonly TextMatch[] = [wanted],
): TextMatch | null {
  const candidates = current.filter((match) => sameMatch(match, wanted));
  const before = seen.filter((match) => sameMatch(match, wanted));
  const rank = before.findIndex((match) => match.from === wanted.from);
  if (rank !== -1 && before.length === candidates.length) return candidates[rank];
  let best: TextMatch | null = null;
  for (const match of candidates) {
    if (!best || Math.abs(match.from - wanted.from) < Math.abs(best.from - wanted.from)) best = match;
  }
  return best;
}
