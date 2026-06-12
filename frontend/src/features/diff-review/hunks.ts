/** Hunk parsing, application, rebase, and minimal-edit logic (spec 47). Pure. */
import type { DiffHunk, LineType } from "./types";

interface WireHunk {
  hunk_id: string;
  header: string;
  old_start: number;
  old_lines: number;
  new_start: number;
  new_lines: number;
  lines: { op: " " | "-" | "+"; text: string }[];
}

const OP_TO_TYPE: Record<string, LineType> = { " ": "ctx", "-": "del", "+": "add" };

export function mapWireHunk(w: WireHunk): DiffHunk {
  return {
    id: w.hunk_id,
    header: w.header,
    oldStart: w.old_start,
    oldLines: w.old_lines,
    newStart: w.new_start,
    newLines: w.new_lines,
    lines: w.lines.map((l) => ({ type: OP_TO_TYPE[l.op] ?? "ctx", text: l.text })),
  };
}

/** The lines a hunk expects in the *old* (base/current) content at its location. */
function oldLinesOf(hunk: DiffHunk): string[] {
  return hunk.lines.filter((l) => l.type !== "add").map((l) => l.text);
}

/** The lines a hunk produces (context kept + additions). */
function newLinesOf(hunk: DiffHunk): string[] {
  return hunk.lines.filter((l) => l.type !== "del").map((l) => l.text);
}

function toLines(content: string): { lines: string[]; trailingNewline: boolean } {
  const trailingNewline = content.endsWith("\n");
  const lines = content.split("\n");
  if (trailingNewline) lines.pop(); // drop the empty element after the final newline
  if (content === "") return { lines: [], trailingNewline: false };
  return { lines, trailingNewline };
}

function join(lines: string[], trailingNewline: boolean): string {
  const body = lines.join("\n");
  return trailingNewline && lines.length > 0 ? `${body}\n` : body;
}

/** Find where `needle` lines occur in `lines`, searching outward from `hint`. -1 if absent. */
export function locate(lines: string[], needle: string[], hint: number): number {
  if (needle.length === 0) return Math.max(0, Math.min(hint, lines.length));
  const maxStart = lines.length - needle.length;
  if (maxStart < 0) return -1;
  for (let d = 0; d <= lines.length; d++) {
    for (const cand of d === 0 ? [hint] : [hint - d, hint + d]) {
      if (cand < 0 || cand > maxStart) continue;
      if (needle.every((n, i) => lines[cand + i] === n)) return cand;
    }
  }
  return -1;
}

export interface RebaseResult {
  target: string;
  appliedHunkIds: string[];
  blockedHunkIds: string[];
}

/**
 * Apply the accepted hunks to `content`, locating each against the *current* content
 * (rebase). Hunks that no longer match are blocked and excluded.
 */
export function rebaseHunks(
  content: string,
  hunks: DiffHunk[],
  accepted: Set<string>,
): RebaseResult {
  const { lines, trailingNewline } = toLines(content);
  const planned: { loc: number; oldCount: number; newLines: string[]; id: string }[] = [];
  const blocked: string[] = [];

  for (const hunk of hunks) {
    if (!accepted.has(hunk.id)) continue;
    const old = oldLinesOf(hunk);
    const loc = locate(lines, old, hunk.oldStart - 1);
    if (loc === -1) {
      blocked.push(hunk.id);
      continue;
    }
    planned.push({ loc, oldCount: old.length, newLines: newLinesOf(hunk), id: hunk.id });
  }

  // Apply bottom-up so earlier line indices stay valid.
  planned.sort((a, b) => b.loc - a.loc);
  const result = lines.slice();
  for (const p of planned) {
    result.splice(p.loc, p.oldCount, ...p.newLines);
  }
  return {
    target: join(result, trailingNewline),
    appliedHunkIds: planned.map((p) => p.id),
    blockedHunkIds: blocked,
  };
}

/** Preview content = accepted hunks applied to the (clean) base. */
export function previewContent(base: string, hunks: DiffHunk[], accepted: Set<string>): string {
  return rebaseHunks(base, hunks, accepted).target;
}

/** Hunks whose old lines no longer match the live content (would be blocked at apply). */
export function blockedAgainst(live: string, hunks: DiffHunk[]): string[] {
  const { lines } = toLines(live);
  return hunks.filter((h) => locate(lines, oldLinesOf(h), h.oldStart - 1) === -1).map((h) => h.id);
}

export interface MinimalEdit {
  start: number;
  deleteLength: number;
  insert: string;
}

/** A minimal single-region edit (common prefix/suffix preserved) from `current` to `target`. */
export function minimalEdit(current: string, target: string): MinimalEdit {
  let p = 0;
  const max = Math.min(current.length, target.length);
  while (p < max && current[p] === target[p]) p++;
  let s = 0;
  while (s < max - p && current[current.length - 1 - s] === target[target.length - 1 - s]) {
    s++;
  }
  return {
    start: p,
    deleteLength: current.length - p - s,
    insert: target.slice(p, target.length - s),
  };
}
