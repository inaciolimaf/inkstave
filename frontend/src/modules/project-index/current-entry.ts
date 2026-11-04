import type { ResolvedItem } from "./resolve-includes";

/**
 * The index of the entry that holds the cursor: the last entry of the open file at or above its line. `-1`
 * when the cursor is above every entry of the file, or no file is open.
 */
export function findCurrentEntry(
  entries: readonly ResolvedItem[],
  openDocId: string | null,
  line: number,
): number {
  if (openDocId === null) return -1;
  let found = -1;
  entries.forEach((entry, index) => {
    if (entry.docId === openDocId && entry.line <= line) found = index;
  });
  return found;
}
