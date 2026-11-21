/** Which two versions the history panel diffs (spec 38). */

/**
 * What the diff compares. One selected version shows what it changed, against the version before it;
 * the first version has none before it, so it is compared with the current text. A second selection
 * compares the two.
 */
export function diffRange(
  primary: number | null,
  compare: number | null,
): { from: number | null; to: number | "current" | null } {
  if (primary === null) return { from: null, to: null };
  if (compare !== null) return { from: Math.min(primary, compare), to: Math.max(primary, compare) };
  if (primary > 1) return { from: primary - 1, to: primary };
  return { from: primary, to: "current" };
}
