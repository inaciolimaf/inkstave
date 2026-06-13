/**
 * CodeMirror extension for `y-codemirror.next`'s remote cursors/selections (spec 32).
 * y-codemirror.next sets each peer's color inline (from awareness `user.color` /
 * `user.colorLight`); this module supplies the layout + the on-hover name label,
 * plus an idle-fade plugin that dims an idle peer's caret on other clients (AC6).
 *
 * Idle fade: y-codemirror.next does not natively consume an `idle` awareness
 * field, so its `YRemoteCaretWidget` DOM carries no idle marker. We read the same
 * `state.idle` field that `OnlineUsers.tsx` uses to dim avatars and, after each
 * view update, tag the caret/label DOM of idle peers with `--idle` classes; a CSS
 * rule then fades them. Peers are matched by their inline caret colour (set by
 * y-codemirror from `user.color`), which is unique per user.
 */
import { ySyncFacet } from "y-codemirror.next";
import { type Extension } from "@codemirror/state";
import { EditorView, ViewPlugin, type ViewUpdate } from "@codemirror/view";

const baseTheme = EditorView.baseTheme({
  ".cm-ySelectionCaret": {
    position: "relative",
    borderLeft: "1px solid black",
    borderRight: "1px solid black",
    marginLeft: "-1px",
    marginRight: "-1px",
    boxSizing: "border-box",
    display: "inline",
  },
  ".cm-ySelectionCaretDot": {
    borderRadius: "50%",
    position: "absolute",
    width: ".4em",
    height: ".4em",
    top: "-.2em",
    left: "-.2em",
    backgroundColor: "inherit",
    transition: "transform .3s ease-in-out",
    boxSizing: "border-box",
  },
  ".cm-ySelectionInfo": {
    position: "absolute",
    top: "-1.05em",
    left: "-1px",
    fontSize: ".75em",
    fontFamily: "ui-sans-serif, system-ui, sans-serif",
    fontStyle: "normal",
    fontWeight: "600",
    lineHeight: "normal",
    userSelect: "none",
    color: "white",
    paddingLeft: "2px",
    paddingRight: "2px",
    zIndex: "101",
    whiteSpace: "nowrap",
    borderRadius: "2px 2px 2px 0",
    opacity: "0",
    transition: "opacity .3s ease-in-out",
    transitionDelay: "0s",
  },
  ".cm-ySelectionCaret:hover > .cm-ySelectionInfo": {
    opacity: "1",
    transitionDelay: "0s",
  },
  // AC6: an idle peer's caret fades on other clients. Hovering still reveals
  // the name label at full opacity (the hover rule above wins via specificity).
  ".cm-ySelectionCaret--idle": {
    opacity: "0.35",
    transition: "opacity .3s ease-in-out",
  },
  ".cm-ySelectionCaret--idle > .cm-ySelectionInfo": {
    opacity: "0",
  },
});

/** Normalise a CSS colour string for comparison (lowercase, no whitespace). */
function normaliseColor(value: string): string {
  return value.replace(/\s+/g, "").toLowerCase();
}

/**
 * Collect the inline caret colours of peers whose `idle` awareness field is set.
 * Returns null when no awareness is available (e.g. outside a y-collab session),
 * in which case the fader is a no-op.
 */
function idleColors(view: EditorView): Set<string> | null {
  const conf = view.state.facet(ySyncFacet) as
    | {
        awareness?: {
          getStates(): Map<number, Record<string, unknown>>;
          doc: { clientID: number };
        };
      }
    | undefined;
  const awareness = conf?.awareness;
  if (!awareness) return null;
  const colors = new Set<string>();
  for (const [clientId, state] of awareness.getStates()) {
    if (clientId === awareness.doc.clientID) continue;
    if (!state.idle) continue;
    const user = state.user as { color?: string } | undefined;
    if (user?.color) colors.add(normaliseColor(user.color));
  }
  return colors;
}

/**
 * After every view update, tag the carets of idle peers so the CSS fade applies.
 * y-codemirror re-renders caret widgets on awareness change (and dispatches a
 * transaction), so this runs whenever idle state flips.
 */
const idleCaretFade = ViewPlugin.fromClass(
  class {
    constructor(view: EditorView) {
      this.apply(view);
    }
    update(update: ViewUpdate) {
      this.apply(update.view);
    }
    apply(view: EditorView) {
      const idle = idleColors(view);
      if (idle === null) return;
      const carets = view.dom.querySelectorAll<HTMLElement>(".cm-ySelectionCaret");
      for (const caret of carets) {
        const color = normaliseColor(caret.style.backgroundColor || caret.style.borderColor || "");
        caret.classList.toggle("cm-ySelectionCaret--idle", color !== "" && idle.has(color));
      }
    }
  },
);

/**
 * The remote-cursor extension: base theme + idle-caret fade. Composed as an
 * array so consumers can add it to their CodeMirror extension list unchanged.
 */
export const remoteCursorTheme: Extension = [baseTheme, idleCaretFade];
