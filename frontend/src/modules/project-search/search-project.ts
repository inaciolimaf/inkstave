/** Searches every document of the project at once (spec 122). Pure, no DOM. */
import { type TextMatch, findMatches } from "./find";

/** A document's text as the project index holds it: live for the open file, fetched for the others. */
export interface SourceText {
  id: string;
  path: string;
  text: string;
}

export interface FileResult {
  docId: string;
  path: string;
  matches: TextMatch[];
}

export interface SearchResults {
  files: FileResult[];
  total: number;
  /** The cap cut the list: there are more matches than `total`. "Replace all" still replaces every one. */
  truncated: boolean;
}

/** Matches listed at most; past it the panel says the list is cut, and the page stays responsive. */
export const MAX_RESULTS = 1000;

export const NO_RESULTS: SearchResults = { files: [], total: 0, truncated: false };

/** The matches of `pattern` in every source, grouped by file in path order. */
export function searchSources(
  sources: readonly SourceText[],
  pattern: RegExp,
  limit = MAX_RESULTS,
): SearchResults {
  const sorted = [...sources].sort((a, b) => a.path.localeCompare(b.path));
  const files: FileResult[] = [];
  let total = 0;
  let truncated = false;
  for (const source of sorted) {
    const left = limit - total;
    // One more than fits says whether the cap cut this file.
    const matches = findMatches(source.text, pattern, left + 1);
    if (matches.length > left) {
      truncated = true;
      matches.length = left;
    }
    if (matches.length > 0) files.push({ docId: source.id, path: source.path, matches });
    total += matches.length;
    if (truncated) break;
  }
  return { files, total, truncated };
}
