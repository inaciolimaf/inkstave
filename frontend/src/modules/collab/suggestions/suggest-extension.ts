/**
 * The editor side of Suggesting mode (spec 119 §5.3). This replaces `y-codemirror.next`'s sync plugin: it does
 * what that plugin does (local edits to the `Y.Text`, remote edits to the view) and, in Suggesting mode, writes
 * the records of §5.2 in the same Yjs transaction as the text. The library's undo manager, remote cursors and
 * undo keymap stay as they are; they key on the sync configuration this plugin shares with them.
 *
 * Spike result (see docs/adr/0119-track-changes.md): `y-codemirror.next` 0.3.5 opens its own transaction inside
 * its update and does not expose it, so a record cannot join the text change there. Replacing the plugin is the
 * closest correct option that keeps undo, remote cursors and the origin the undo manager tracks.
 */
import { Annotation, type ChangeSet, EditorState, type Extension, StateEffect } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView, ViewPlugin, type ViewUpdate } from "@codemirror/view";
import { ySyncFacet } from "y-codemirror.next";
import type { Awareness } from "y-protocols/awareness";
import type * as Y from "yjs";

import { type Plan, type PlanOp, type TextChange, planEdit } from "./record";
import {
  type SuggestionAuthor,
  type SuggestionMap,
  encodePosition,
  newSuggestionId,
  ownInsertions,
  readSuggestions,
} from "./model";
import { suggestionDecorations, suggestionTheme } from "./decorations";
import { suggestPopover } from "./popover";

/** The Suggesting switch: whether it is on, and whether the editor may act on it (synced, and writable). */
export class SuggestController {
  private on = false;
  private enabled = false;
  private readonly listeners = new Set<() => void>();
  /** Called when an edit is refused because its deletion is too large. */
  onBlocked: () => void = () => {};

  constructor(
    private readonly getAuthor: () => SuggestionAuthor | null,
    private readonly awareness: Awareness | null,
  ) {}

  get author(): SuggestionAuthor | null {
    return this.getAuthor();
  }

  /** The switch as the user set it, for `useSyncExternalStore`. */
  getSnapshot = (): boolean => this.on;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** Whether an edit made now is recorded as a suggestion. */
  isSuggesting(): boolean {
    return this.on && this.enabled && this.getAuthor() !== null;
  }

  setSuggesting(on: boolean): void {
    if (on === this.on) return;
    this.on = on;
    this.publish();
  }

  setEnabled(enabled: boolean): void {
    if (enabled === this.enabled) return;
    this.enabled = enabled;
    this.publish();
  }

  private publish(): void {
    const awareness = this.awareness;
    if (awareness) {
      try {
        awareness.setLocalState({ ...(awareness.getLocalState() ?? {}), suggesting: this.isSuggesting() });
      } catch {
        /* awareness already torn down */
      }
    }
    for (const listener of this.listeners) listener();
  }
}

export interface SuggestOptions {
  ytext: Y.Text;
  suggestions: SuggestionMap;
  controller: SuggestController;
  /** False for a viewer: suggestions are shown, but not accepted or rejected. */
  canDecide: boolean;
}

const refreshSuggestions = StateEffect.define<null>();
/** Marks a transaction that brings a remote change into the view, so it is not written back. */
const remoteChange = Annotation.define<true>();

function changesOf(changes: ChangeSet): TextChange[] {
  const out: TextChange[] = [];
  changes.iterChanges((fromA, toA, _fromB, _toB, inserted) => {
    out.push({ from: fromA, to: toA, insert: inserted.sliceString(0, inserted.length, "\n") });
  });
  return out;
}

/** The changes of a Yjs text event, as CodeMirror changes in the coordinates of the view before it. */
function remoteChangesOf(delta: Array<{ insert?: unknown; delete?: number; retain?: number }>): TextChange[] {
  const changes: TextChange[] = [];
  let position = 0;
  for (const part of delta) {
    if (part.insert !== undefined) {
      changes.push({ from: position, to: position, insert: String(part.insert) });
    } else if (part.delete !== undefined) {
      changes.push({ from: position, to: position + part.delete, insert: "" });
      position += part.delete;
    } else {
      position += part.retain ?? 0;
    }
  }
  return changes;
}

function planFor(
  options: SuggestOptions,
  changes: TextChange[],
  removed: (from: number, to: number) => string,
): Plan {
  const author = options.controller.isSuggesting() ? options.controller.author : null;
  return planEdit({
    changes,
    own: author ? ownInsertions(options.ytext, options.suggestions, author.id) : [],
    author,
    now: new Date().toISOString(),
    newId: () => newSuggestionId(),
    removed,
  });
}

/** Writes one planned operation. Record operations need an author; a plain edit has none and writes text only. */
function applyOp(
  ytext: Y.Text,
  suggestions: SuggestionMap,
  op: PlanOp,
  author: SuggestionAuthor | null,
  now: string,
): void {
  switch (op.kind) {
    case "text-delete":
      ytext.delete(op.from, op.to - op.from);
      return;
    case "text-insert":
      ytext.insert(op.at, op.text);
      return;
    case "insertion-set":
      if (!author) return;
      suggestions.set(op.id, {
        kind: "insert",
        author_id: author.id,
        author_name: author.name,
        created_at: op.createdAt,
        start: encodePosition(ytext, op.from, 0),
        end: encodePosition(ytext, op.to, -1),
      });
      return;
    case "insertion-remove":
      suggestions.delete(op.id);
      return;
    case "deletion-add":
      if (!author) return;
      suggestions.set(op.id, {
        kind: "delete",
        author_id: author.id,
        author_name: author.name,
        created_at: now,
        at: encodePosition(ytext, op.at, 0),
        text: op.text,
      });
  }
}

/** The text and the records of one local edit, written in one Yjs transaction with the sync origin. */
function writeLocal(options: SuggestOptions, origin: unknown, plan: Plan, now: string): void {
  const doc = options.ytext.doc;
  const author = options.controller.isSuggesting() ? options.controller.author : null;
  if (!doc || plan.blocked) return;
  doc.transact(() => {
    for (const op of plan.ops) applyOp(options.ytext, options.suggestions, op, author, now);
  }, origin);
}

class SuggestSyncPlugin {
  decorations: DecorationSet = Decoration.none;
  private readonly origin: unknown;
  private destroyed = false;
  private readonly onText: (event: Y.YTextEvent, transaction: Y.Transaction) => void;
  private readonly onMap: (event: unknown, transaction: Y.Transaction) => void;

  constructor(
    private readonly view: EditorView,
    private readonly options: SuggestOptions,
  ) {
    this.origin = view.state.facet(ySyncFacet);
    this.onText = (event, transaction) => {
      if (transaction.origin === this.origin) return;
      const changes = remoteChangesOf(
        event.delta as Array<{ insert?: unknown; delete?: number; retain?: number }>,
      );
      if (changes.length > 0 && !this.destroyed) {
        this.view.dispatch({ changes, annotations: [remoteChange.of(true)] });
      }
    };
    this.onMap = (_event, transaction) => {
      if (transaction.origin === this.origin || this.destroyed) return;
      this.view.dispatch({ effects: refreshSuggestions.of(null) });
    };
    options.ytext.observe(this.onText);
    options.suggestions.observe(this.onMap);
  }

  update(update: ViewUpdate): void {
    const remote = update.transactions.some((tr) => tr.annotation(remoteChange) !== undefined);
    if (update.docChanged && !remote) {
      const startState = update.startState;
      const changes = changesOf(update.changes);
      if (changes.length > 0) {
        const plan = planFor(this.options, changes, (from, to) => startState.sliceDoc(from, to));
        writeLocal(this.options, this.origin, plan, new Date().toISOString());
      }
    }
    const refresh = update.transactions.some((tr) =>
      tr.effects.some((effect) => effect.is(refreshSuggestions)),
    );
    if (update.docChanged || refresh) {
      const placed = readSuggestions(this.options.ytext, this.options.suggestions);
      this.decorations = suggestionDecorations(placed, update.state.doc.length);
    }
  }

  destroy(): void {
    this.destroyed = true;
    this.options.ytext.unobserve(this.onText);
    this.options.suggestions.unobserve(this.onMap);
  }
}

/** Refuses an edit that would delete too much to record. The view keeps the text as it was. */
const suggestFilter = (options: SuggestOptions): Extension =>
  EditorState.transactionFilter.of((transaction) => {
    if (!transaction.docChanged || transaction.annotation(remoteChange) !== undefined) return transaction;
    if (!options.controller.isSuggesting()) return transaction;
    const startState = transaction.startState;
    const plan = planFor(options, changesOf(transaction.changes), (from, to) =>
      startState.sliceDoc(from, to),
    );
    if (!plan.blocked) return transaction;
    options.controller.onBlocked();
    return [];
  });

/** Everything the editor needs for Suggesting mode: the sync plugin, the refusal, the popover and the marks. */
export function suggestExtension(options: SuggestOptions): Extension {
  return [
    ViewPlugin.define((view) => new SuggestSyncPlugin(view, options), {
      decorations: (plugin) => plugin.decorations,
    }),
    suggestFilter(options),
    suggestPopover(options),
    suggestionTheme,
  ];
}
