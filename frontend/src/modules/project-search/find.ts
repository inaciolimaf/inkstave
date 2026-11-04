/** Finds every match of a pattern in a text, with its line and a short preview (spec 122). Pure, no DOM. */

export interface TextMatch {
  /** Offsets in the text, in UTF-16 code units, the unit Yjs and CodeMirror count in. */
  from: number;
  to: number;
  /** 1-based line of the match's start, and its 0-based column in that line. */
  line: number;
  column: number;
  /** The matched text, and the capture groups the replacement can refer to. */
  text: string;
  groups: (string | undefined)[];
  named: Record<string, string | undefined>;
  /** The whole line the match starts on, which tells the same match apart after the text moved. */
  lineText: string;
}

/** Offset of the first character of each line. */
function lineStarts(text: string): number[] {
  const starts = [0];
  for (let i = text.indexOf("\n"); i !== -1; i = text.indexOf("\n", i + 1)) starts.push(i + 1);
  return starts;
}

/** Index of the line that holds `offset`, by binary search over `starts`. */
function lineIndexOf(starts: readonly number[], offset: number): number {
  let low = 0;
  let high = starts.length - 1;
  while (low < high) {
    const mid = (low + high + 1) >> 1;
    if (starts[mid] <= offset) low = mid;
    else high = mid - 1;
  }
  return low;
}

/**
 * Every non-empty match of `pattern` in `text`, at most `limit`. Empty matches (`^`, `a*` between letters) are
 * skipped: there is nothing to show or replace. `pattern` must carry the `g` flag, as `buildMatcher` gives it.
 */
export function findMatches(text: string, pattern: RegExp, limit = Number.POSITIVE_INFINITY): TextMatch[] {
  const starts = lineStarts(text);
  const matches: TextMatch[] = [];
  for (const found of text.matchAll(pattern)) {
    if (matches.length >= limit) break;
    if (found[0] === "") continue;
    const from = found.index;
    const index = lineIndexOf(starts, from);
    const lineEnd = index + 1 < starts.length ? starts[index + 1] - 1 : text.length;
    matches.push({
      from,
      to: from + found[0].length,
      line: index + 1,
      column: from - starts[index],
      text: found[0],
      groups: found.slice(1),
      named: { ...found.groups },
      lineText: text.slice(starts[index], lineEnd),
    });
  }
  return matches;
}

/** How much of the line is kept before the match in a preview, so a match far along a long line is visible. */
const PREVIEW_BEFORE = 30;
const PREVIEW_AFTER = 80;

export interface MatchPreview {
  before: string;
  match: string;
  after: string;
}

/** The match in its line, cut around it. A match that runs past its line shows its first line only. */
export function previewOf(match: TextMatch): MatchPreview {
  const line = match.lineText;
  const end = Math.min(match.column + match.text.length, line.length);
  const start = Math.max(0, match.column - PREVIEW_BEFORE);
  return {
    before: (start > 0 ? "…" : "") + line.slice(start, match.column).trimStart(),
    match: line.slice(match.column, end),
    after: line.slice(end, end + PREVIEW_AFTER),
  };
}
