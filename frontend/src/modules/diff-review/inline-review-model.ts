/** The state of an inline review: where each hunk sits in the text and what was decided (spec 110). Pure. */
import { locate, oldLinesOf } from "./hunks";
import type { DecisionLists } from "./api";
import type { DiffHunk } from "./types";

export type Decision = "open" | "accepted" | "rejected" | "stale";

export interface ReviewHunk {
  hunk: DiffHunk;
  decision: Decision;
  /** The old lines no longer match the text: the hunk can only be rejected. */
  blocked: boolean;
  /** A write for this hunk is in flight. */
  busy: boolean;
  /** 0-based line where the hunk's old lines start (where it is drawn when blocked). */
  line: number;
}

/** Decisions carried over from an earlier opening of the same proposal, by hunk id. */
export type Decided = Record<string, Decision>;

/** What a review shows of itself: the proposal, its hunks, the keyboard's hunk and whether viewing only. */
export interface ReviewSnapshot {
  proposalId: string;
  hunks: ReviewHunk[];
  readOnly: boolean;
  active: number;
}

/** What the review's controls and keys do. Each call is a decision on the hunk, or on all of them. */
export interface ReviewActions {
  accept(hunkId: string): void;
  reject(hunkId: string): void;
  acceptAll(): void;
  rejectAll(): void;
  /** Records the outcome once every hunk is decided, then closes the review. */
  settle(): void;
  close(): void;
  /** Called after each change to the review, so the bar and the remembered decisions follow it. */
  onChange(review: ReviewSnapshot): void;
}

/**
 * Where the hunk's old lines start in `lines`, searching outward from `hint`; `-1` when they are gone.
 * A hunk with no old lines (a pure insertion) is placed at the hint.
 */
export function placeHunk(lines: string[], hunk: DiffHunk, hint: number): number {
  return locate(lines, oldLinesOf(hunk), hint);
}

/** A hunk's display line: where it was found, else the line the proposal names, clamped to the text. */
export function displayLine(
  lines: string[],
  hunk: DiffHunk,
  hint: number,
): { line: number; blocked: boolean } {
  const last = lines.length - 1;
  const found = placeHunk(lines, hunk, hint);
  if (found === -1) return { line: Math.max(0, Math.min(hint, last)), blocked: true };
  return { line: Math.min(found, last), blocked: false };
}

export function pendingHunks(hunks: ReviewHunk[]): ReviewHunk[] {
  return hunks.filter((h) => h.decision === "open");
}

export function allDecided(hunks: ReviewHunk[]): boolean {
  return hunks.every((h) => h.decision !== "open");
}

/** The three lists the outcome route takes: every decided hunk, once, in its list. */
export function outcomeLists(hunks: ReviewHunk[]): DecisionLists {
  const lists: DecisionLists = { accepted: [], rejected: [], stale: [] };
  for (const h of hunks) {
    if (h.decision !== "open") lists[h.decision].push(h.hunk.id);
  }
  return lists;
}

export function decisionsOf(hunks: ReviewHunk[]): Decided {
  return Object.fromEntries(hunks.map((h) => [h.hunk.id, h.decision]));
}

/** The first hunk still open at or after `from`, wrapping to the start; `from` when none is open. */
export function nextOpen(hunks: ReviewHunk[], from: number): number {
  for (let step = 0; step < hunks.length; step++) {
    const index = (from + step) % hunks.length;
    if (hunks[index]!.decision === "open") return index;
  }
  return from;
}
