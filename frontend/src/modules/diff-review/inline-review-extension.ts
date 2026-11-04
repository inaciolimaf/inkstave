/**
 * The proposal drawn inside the text (spec 110): removed lines struck through on a red tint, added text in
 * green under them, and a toolbar per open hunk with Accept and Reject. The text itself is not changed here;
 * a decision is written by the review's actions, through the CRDT.
 */
import {
  type Extension,
  Prec,
  type Range,
  StateEffect,
  StateField,
  type Text,
  type Transaction,
} from "@codemirror/state";
import {
  Decoration,
  type DecorationSet,
  EditorView,
  ViewPlugin,
  type ViewUpdate,
  keymap,
} from "@codemirror/view";

import { oldLinesOf } from "./hunks";
import {
  type Decided,
  type Decision,
  type ReviewActions,
  type ReviewHunk,
  displayLine,
  nextOpen,
} from "./inline-review-model";
import { AddedWidget, ToolbarWidget } from "./inline-review-widgets";
import type { DiffHunk } from "./types";

/** A hunk with its document range: the old lines (`from`..`to`), or the line where they were expected. */
export interface PlacedHunk extends ReviewHunk {
  from: number;
  to: number;
}

export interface InlineReview {
  proposalId: string;
  path: string;
  readOnly: boolean;
  /** Index of the hunk the keyboard is on. */
  active: number;
  hunks: PlacedHunk[];
  actions: ReviewActions;
  decorations: DecorationSet;
}

export interface StartPayload {
  proposalId: string;
  path: string;
  readOnly: boolean;
  hunks: DiffHunk[];
  decided: Decided;
  actions: ReviewActions;
}

export interface HunkPatch {
  hunkId: string;
  patch: Partial<Pick<ReviewHunk, "decision" | "busy" | "blocked">>;
}

export const startInlineReview = StateEffect.define<StartPayload>();
export const stopInlineReview = StateEffect.define<null>();
export const updateHunk = StateEffect.define<HunkPatch>();
export const setActiveHunk = StateEffect.define<number>();

/** The document range of a hunk: its first old line to its last (empty when blocked or a pure insertion). */
function positioned(doc: Text, hunk: ReviewHunk): PlacedHunk {
  const oldCount = oldLinesOf(hunk.hunk).length;
  const from = doc.line(hunk.line + 1).from;
  const to = hunk.blocked || oldCount === 0 ? from : doc.line(Math.min(hunk.line + oldCount, doc.lines)).to;
  return { ...hunk, from, to };
}

function createReview(payload: StartPayload, doc: Text): InlineReview {
  const lines = doc.toString().split("\n");
  const hunks = payload.hunks.map((hunk) => {
    const decision: Decision = payload.decided[hunk.id] ?? "open";
    const placed =
      decision === "open" ? displayLine(lines, hunk, hunk.oldStart - 1) : { line: 0, blocked: false };
    return positioned(doc, { hunk, decision, busy: false, ...placed });
  });
  return {
    proposalId: payload.proposalId,
    path: payload.path,
    readOnly: payload.readOnly,
    active: nextOpen(hunks, 0),
    hunks,
    actions: payload.actions,
    decorations: Decoration.none,
  };
}

/** After a change: a hunk the change touched, or one that was blocked, is found again; the rest move with the text. */
function relocate(review: InlineReview, tr: Transaction): InlineReview {
  const lines = tr.newDoc.toString().split("\n");
  const changed: [number, number][] = [];
  tr.changes.iterChangedRanges((fromA, toA) => changed.push([fromA, toA]));
  const hunks = review.hunks.map((h) => (h.decision === "open" ? relocateHunk(h, tr, lines, changed) : h));
  return { ...review, hunks };
}

function relocateHunk(
  h: PlacedHunk,
  tr: Transaction,
  lines: string[],
  changed: [number, number][],
): PlacedHunk {
  const mappedFrom = tr.changes.mapPos(h.from, 1);
  const touched = changed.some(([a, b]) => a <= h.to && b >= h.from);
  if (!touched && !h.blocked) {
    return positioned(tr.newDoc, { ...h, line: tr.newDoc.lineAt(mappedFrom).number - 1 });
  }
  const hint = h.blocked ? h.hunk.oldStart - 1 : tr.newDoc.lineAt(mappedFrom).number - 1;
  return positioned(tr.newDoc, { ...h, ...displayLine(lines, h.hunk, hint) });
}

function patchHunk(review: InlineReview, { hunkId, patch }: HunkPatch): InlineReview {
  const hunks = review.hunks.map((h) => (h.hunk.id === hunkId ? { ...h, ...patch } : h));
  const active = hunks[review.active]?.decision === "open" ? review.active : nextOpen(hunks, review.active);
  return { ...review, hunks, active };
}

const REMOVED = "cm-review-removed";

/** The widgets and line marks of the open hunks. Decided hunks draw nothing. */
function decorate(review: InlineReview, doc: Text): DecorationSet {
  const ranges: Range<Decoration>[] = [];
  review.hunks.forEach((h, index) => {
    if (h.decision !== "open") return;
    ranges.push(toolbarRange(review, h, index));
    if (h.blocked) return;
    const added = h.hunk.lines.filter((l) => l.type === "add").map((l) => l.text);
    const oldCount = oldLinesOf(h.hunk).length;
    let oldIndex = 0;
    for (const line of h.hunk.lines) {
      if (line.type === "add") continue;
      if (line.type === "del") {
        ranges.push(Decoration.line({ class: REMOVED }).range(doc.line(h.line + oldIndex + 1).from));
      }
      oldIndex += 1;
    }
    if (added.length > 0) {
      const at = oldCount > 0 ? h.to : h.from;
      ranges.push(
        Decoration.widget({ widget: new AddedWidget(added), block: true, side: oldCount ? 1 : -1 }).range(at),
      );
    }
  });
  return Decoration.set(ranges, true);
}

function toolbarRange(review: InlineReview, h: PlacedHunk, index: number): Range<Decoration> {
  const widget = new ToolbarWidget({
    hunkId: h.hunk.id,
    index: index + 1,
    total: review.hunks.length,
    blocked: h.blocked,
    busy: h.busy,
    active: index === review.active,
    readOnly: review.readOnly,
    actions: review.actions,
  });
  return Decoration.widget({ widget, block: true, side: -2 }).range(h.from);
}

function withDecorations(review: InlineReview, doc: Text): InlineReview {
  return { ...review, decorations: decorate(review, doc) };
}

export const inlineReviewField = StateField.define<InlineReview | null>({
  create: () => null,
  update(review, tr) {
    let next = review;
    for (const effect of tr.effects) {
      if (effect.is(startInlineReview)) next = createReview(effect.value, tr.state.doc);
      else if (effect.is(stopInlineReview)) next = null;
      else if (next && effect.is(updateHunk)) next = patchHunk(next, effect.value);
      else if (next && effect.is(setActiveHunk)) next = { ...next, active: effect.value };
    }
    if (!next) return null;
    if (tr.docChanged && next === review) next = relocate(next, tr);
    return next === review ? review : withDecorations(next, tr.state.doc);
  },
  provide: (field) => EditorView.decorations.from(field, (review) => review?.decorations ?? Decoration.none),
});

/** Scrolls to a hunk and makes it the keyboard's current one. */
export function focusHunk(view: EditorView, index: number): void {
  const review = view.state.field(inlineReviewField);
  const hunk = review?.hunks[index];
  if (!review || !hunk) return;
  view.dispatch({
    effects: [setActiveHunk.of(index), EditorView.scrollIntoView(hunk.from, { y: "center" })],
  });
}

/** The next open hunk in `direction` (1 or -1), wrapping around. */
export function moveReviewHunk(view: EditorView, direction: 1 | -1): boolean {
  const review = view.state.field(inlineReviewField);
  if (!review) return false;
  const count = review.hunks.length;
  for (let step = 1; step <= count; step++) {
    const index = (((review.active + direction * step) % count) + count) % count;
    if (review.hunks[index]!.decision === "open") {
      focusHunk(view, index);
      return true;
    }
  }
  return false;
}

function decideActive(view: EditorView, kind: "accept" | "reject"): boolean {
  const review = view.state.field(inlineReviewField);
  const hunk = review?.hunks[review.active];
  if (!review || !hunk || review.readOnly || hunk.decision !== "open" || hunk.busy) return false;
  if (kind === "accept") review.actions.accept(hunk.hunk.id);
  else review.actions.reject(hunk.hunk.id);
  return true;
}

// Above the editor's own keys, so Alt+Backspace is the review's while one is open.
const reviewKeys = Prec.high(
  keymap.of([
    { key: "Alt-]", run: (view) => moveReviewHunk(view, 1) },
    { key: "Alt-[", run: (view) => moveReviewHunk(view, -1) },
    { key: "Alt-Enter", run: (view) => decideActive(view, "accept") },
    { key: "Alt-Backspace", run: (view) => decideActive(view, "reject") },
  ]),
);

/** Tells the review's owner about every change to it. It never changes the document. */
const reviewReporter = ViewPlugin.fromClass(
  class {
    update(update: ViewUpdate) {
      const before = update.startState.field(inlineReviewField);
      const after = update.state.field(inlineReviewField);
      if (after && after !== before) after.actions.onChange(after);
    }
  },
);

const reviewTheme = EditorView.baseTheme({
  [`.${REMOVED}`]: {
    backgroundColor: "hsl(var(--error-soft))",
    color: "hsl(var(--error-text))",
    textDecoration: "line-through",
  },
  ".cm-review-added": {
    backgroundColor: "hsl(var(--success-soft))",
    color: "hsl(var(--success-text))",
    whiteSpace: "pre-wrap",
  },
});

/** The inline review, always installed in the editor and inert until a review starts. */
export const inlineReviewExtension: Extension = [inlineReviewField, reviewReporter, reviewKeys, reviewTheme];
