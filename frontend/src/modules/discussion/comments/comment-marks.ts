/**
 * The highlights of open comment threads in the text (spec 118). Each thread's anchors are resolved
 * against the Y.Text again after every change, so a highlight follows its text. A click on a highlight
 * selects its thread; the editor keymap starts a new comment with Mod-Alt-m.
 */
import { type Extension, StateEffect } from "@codemirror/state";
import {
  Decoration,
  type DecorationSet,
  EditorView,
  keymap,
  ViewPlugin,
  type ViewUpdate,
} from "@codemirror/view";
import type * as Y from "yjs";

import { resolveAnchor } from "./anchors";

export interface CommentMark {
  id: string;
  anchorStart: string;
  anchorEnd: string;
}

export interface CommentMarkHandlers {
  onSelect: (threadId: string) => void;
  onNew: () => boolean;
}

/** The open threads of the document and the one that is selected. */
export const setCommentMarks = StateEffect.define<{ marks: CommentMark[]; selectedId: string | null }>();

/** Re-resolves the anchors; sent when the Y.Text changed outside a CodeMirror transaction. */
const refreshCommentMarks = StateEffect.define<null>();

function buildDecorations(
  view: EditorView,
  text: Y.Text,
  marks: CommentMark[],
  selectedId: string | null,
): DecorationSet {
  const ranges = [];
  for (const mark of marks) {
    const range = resolveAnchor(text, mark.anchorStart, mark.anchorEnd);
    if (!range || range.to > view.state.doc.length) continue;
    const selected = mark.id === selectedId;
    ranges.push(
      Decoration.mark({
        class: selected ? "cm-comment-mark cm-comment-mark-selected" : "cm-comment-mark",
        attributes: { "data-thread-id": mark.id },
      }).range(range.from, range.to),
    );
  }
  return Decoration.set(ranges, true);
}

class CommentMarkPlugin {
  decorations: DecorationSet = Decoration.none;
  private marks: CommentMark[] = [];
  private selectedId: string | null = null;
  private destroyed = false;
  private readonly onYChange: () => void;

  constructor(
    private readonly view: EditorView,
    private readonly text: Y.Text,
  ) {
    // A remote edit reaches the text as a CodeMirror change too, but the Y.Text may not hold it yet
    // when this view's update runs. Re-resolving on the next microtask sees the settled text.
    this.onYChange = () =>
      queueMicrotask(() => {
        if (!this.destroyed) this.view.dispatch({ effects: refreshCommentMarks.of(null) });
      });
    text.observe(this.onYChange);
  }

  update(update: ViewUpdate): void {
    let changed = update.docChanged;
    for (const transaction of update.transactions) {
      for (const effect of transaction.effects) {
        if (effect.is(setCommentMarks)) {
          this.marks = effect.value.marks;
          this.selectedId = effect.value.selectedId;
          changed = true;
        } else if (effect.is(refreshCommentMarks)) {
          changed = true;
        }
      }
    }
    if (changed) this.decorations = buildDecorations(update.view, this.text, this.marks, this.selectedId);
  }

  destroy(): void {
    this.destroyed = true;
    this.text.unobserve(this.onYChange);
  }
}

/** The mark decorations, the click handler and the new-comment key, for one Y.Text. */
export function commentMarks(text: Y.Text, handlers: { current: CommentMarkHandlers }): Extension {
  const plugin = ViewPlugin.define((view) => new CommentMarkPlugin(view, text), {
    decorations: (instance) => instance.decorations,
    eventHandlers: {
      mousedown(event) {
        const target = event.target instanceof Element ? event.target.closest("[data-thread-id]") : null;
        const threadId = target?.getAttribute("data-thread-id");
        if (threadId) handlers.current.onSelect(threadId);
      },
    },
  });
  return [
    plugin,
    keymap.of([{ key: "Mod-Alt-m", run: () => handlers.current.onNew() }]),
    EditorView.baseTheme({
      ".cm-comment-mark": {
        backgroundColor: "hsl(var(--warning-soft))",
        borderBottom: "2px solid hsl(var(--warning))",
        cursor: "pointer",
      },
      ".cm-comment-mark-selected": {
        backgroundColor: "hsl(var(--warning) / 0.35)",
      },
    }),
  ];
}
