/**
 * The rules of spec 119 §5.2, as a pure planner. It takes one CodeMirror edit (the changed ranges, in the
 * coordinates of the text before the edit) and the caller's own insertions, and returns the operations that
 * apply it: text edits and record edits, in order, each in the coordinates the text has at that step. The
 * sync plugin runs them inside one Yjs transaction, so one undo reverts the text and its records together.
 *
 * Nothing here reads Yjs. The planner tracks the insertions' ranges itself while it walks the change.
 */
import { SUGGESTION_TEXT_MAX_CHARS, type OwnInsertion, type SuggestionAuthor } from "./model";

interface TextRange {
  from: number;
  to: number;
}

/** One changed range: `from`..`to` of the old text is replaced by `insert`. Ascending, not overlapping. */
export interface TextChange {
  from: number;
  to: number;
  insert: string;
}

export type PlanOp =
  | { kind: "text-delete"; from: number; to: number }
  | { kind: "text-insert"; at: number; text: string }
  /** Creates or re-creates the caller's insertion `id` over `from`..`to`. */
  | { kind: "insertion-set"; id: string; from: number; to: number; createdAt: string }
  | { kind: "insertion-remove"; id: string }
  /** Records a deletion of `text` at `at`. */
  | { kind: "deletion-add"; id: string; at: number; text: string };

export interface PlanInput {
  changes: TextChange[];
  /** The caller's insertions in the text as it is before the edit. */
  own: OwnInsertion[];
  /** The caller, when Suggesting is on; null for a plain edit, which records nothing. */
  author: SuggestionAuthor | null;
  /** The time the records are made at, as an ISO string. */
  now: string;
  newId: () => string;
  /** The text removed from `from` to `to` in the text before the edit. */
  removed: (from: number, to: number) => string;
  maxDeletedChars?: number;
}

export interface Plan {
  ops: PlanOp[];
  /** True when the deletion is over the limit: the edit must not be applied. */
  blocked: boolean;
}

/** The parts of `start`..`end` that no own insertion covers, in order. */
function uncovered(own: OwnInsertion[], start: number, end: number): TextRange[] {
  const gaps: TextRange[] = [];
  let position = start;
  for (const range of own) {
    if (range.to <= start || range.from >= end) continue;
    const covered = Math.max(range.from, start);
    if (covered > position) gaps.push({ from: position, to: covered });
    position = Math.max(position, Math.min(range.to, end));
  }
  if (position < end) gaps.push({ from: position, to: end });
  return gaps;
}

/** Shrinks, removes or shifts the own insertions for a deletion of `start`..`end`, and emits their record edits. */
function collapse(own: OwnInsertion[], start: number, end: number, ops: PlanOp[]): OwnInsertion[] {
  const size = end - start;
  const result: OwnInsertion[] = [];
  for (const range of own) {
    if (range.to <= start) {
      result.push(range);
      continue;
    }
    if (range.from >= end) {
      result.push({ ...range, from: range.from - size, to: range.to - size });
      continue;
    }
    const from = Math.min(range.from, start);
    const to = range.to >= end ? range.to - size : start;
    if (to <= from) {
      ops.push({ kind: "insertion-remove", id: range.id });
      continue;
    }
    ops.push({ kind: "insertion-set", id: range.id, from, to, createdAt: range.createdAt });
    result.push({ ...range, from, to });
  }
  return result;
}

/**
 * The caller's insertions after `text` (of `length`) went in at `at`. Typing touching or inside an own
 * insertion grows it; anywhere else starts a new one. Insertions after `at` move.
 */
function grow(
  own: OwnInsertion[],
  at: number,
  length: number,
  input: PlanInput,
  ops: PlanOp[],
): OwnInsertion[] {
  const result: OwnInsertion[] = [];
  let grown = false;
  for (const range of own) {
    if (!grown && range.from <= at && at <= range.to) {
      grown = true;
      const to = range.to + length;
      ops.push({ kind: "insertion-set", id: range.id, from: range.from, to, createdAt: range.createdAt });
      result.push({ ...range, to });
    } else {
      result.push(range.from >= at ? { ...range, from: range.from + length, to: range.to + length } : range);
    }
  }
  if (!grown && input.author) {
    const created = { id: input.newId(), from: at, to: at + length, createdAt: input.now };
    ops.push({ kind: "insertion-set", ...created });
    result.push(created);
    result.sort((a, b) => a.from - b.from);
  }
  return result;
}

/** Plans the operations of one edit. A plain edit (no author) yields the text operations only. */
export function planEdit(input: PlanInput): Plan {
  const maxDeleted = input.maxDeletedChars ?? SUGGESTION_TEXT_MAX_CHARS;
  const ops: PlanOp[] = [];
  let own = input.own.map((range) => ({ ...range }));
  let shift = 0;
  let deleted = 0;
  for (const change of input.changes) {
    const start = change.from + shift;
    const removedLength = change.to - change.from;
    if (removedLength > 0) {
      const end = start + removedLength;
      ops.push({ kind: "text-delete", from: start, to: end });
      if (input.author) {
        const removedText = input.removed(change.from, change.to);
        const gaps = uncovered(own, start, end);
        const text = gaps.map((gap) => removedText.slice(gap.from - start, gap.to - start)).join("");
        own = collapse(own, start, end, ops);
        if (text.length > 0) {
          deleted += text.length;
          ops.push({ kind: "deletion-add", id: input.newId(), at: start, text });
        }
      }
    }
    if (change.insert.length > 0) {
      ops.push({ kind: "text-insert", at: start, text: change.insert });
      if (input.author) own = grow(own, start, change.insert.length, input, ops);
    }
    shift += change.insert.length - removedLength;
  }
  if (deleted > maxDeleted) return { ops: [], blocked: true };
  return { ops, blocked: false };
}
