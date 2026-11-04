/** The widgets drawn into the text for a review: a hunk's toolbar, and the lines a hunk adds (spec 110). */
import { WidgetType } from "@codemirror/view";

import i18n from "@/i18n/config";

import type { ReviewActions } from "./inline-review-model";

const BUTTON =
  "inline-flex min-h-11 min-w-11 items-center justify-center gap-1 rounded border border-control-edge bg-background px-3 text-small font-medium hover:bg-accent disabled:opacity-50 sm:min-h-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export interface ToolbarState {
  hunkId: string;
  index: number;
  total: number;
  blocked: boolean;
  busy: boolean;
  active: boolean;
  readOnly: boolean;
  actions: ReviewActions;
}

/** The hunk's toolbar, above its region. Its buttons are plain DOM, so the editor ignores events in them. */
export class ToolbarWidget extends WidgetType {
  constructor(private readonly state: ToolbarState) {
    super();
  }

  eq(other: ToolbarWidget): boolean {
    const a = this.state;
    const b = other.state;
    return (
      other.state.actions === a.actions &&
      b.hunkId === a.hunkId &&
      b.index === a.index &&
      b.total === a.total &&
      b.blocked === a.blocked &&
      b.busy === a.busy &&
      b.active === a.active &&
      b.readOnly === a.readOnly
    );
  }

  toDOM(): HTMLElement {
    const s = this.state;
    const bar = document.createElement("div");
    const ring = s.active ? " ring-2 ring-inset ring-ring" : "";
    bar.className = `cm-review-toolbar flex flex-wrap items-center gap-2 border-y border-border bg-muted px-3 py-1${ring}`;
    bar.dataset.hunkId = s.hunkId;
    const counter = document.createElement("span");
    counter.className = "font-medium tabular-nums";
    counter.textContent = i18n.t("inline.counter", { ns: "review", index: s.index, total: s.total });
    bar.append(counter);
    if (s.blocked) {
      const note = document.createElement("span");
      note.className = "text-error-text";
      note.textContent = i18n.t("inline.blocked", { ns: "review" });
      bar.append(note);
    }
    if (!s.readOnly) {
      if (!s.blocked) bar.append(this.button("accept"));
      bar.append(this.button("reject"));
    }
    return bar;
  }

  private button(kind: "accept" | "reject"): HTMLButtonElement {
    const s = this.state;
    const button = document.createElement("button");
    button.type = "button";
    button.className = BUTTON;
    button.disabled = s.busy;
    button.setAttribute(
      "aria-label",
      i18n.t(kind === "accept" ? "inline.acceptHunk" : "inline.rejectHunk", { ns: "review", index: s.index }),
    );
    const glyph = document.createElement("span");
    glyph.setAttribute("aria-hidden", "true");
    glyph.textContent = kind === "accept" ? "✓" : "✗";
    const label = document.createElement("span");
    label.textContent = i18n.t(kind === "accept" ? "inline.accept" : "inline.reject", { ns: "review" });
    button.append(glyph, label);
    button.addEventListener("click", () => {
      if (kind === "accept") s.actions.accept(s.hunkId);
      else s.actions.reject(s.hunkId);
    });
    return button;
  }

  ignoreEvent(): boolean {
    return true;
  }
}

/** The lines a hunk adds, in green, where they will go. */
export class AddedWidget extends WidgetType {
  constructor(private readonly lines: string[]) {
    super();
  }

  eq(other: AddedWidget): boolean {
    return other.lines.join("\n") === this.lines.join("\n");
  }

  toDOM(): HTMLElement {
    const block = document.createElement("div");
    block.className = "cm-review-added";
    for (const line of this.lines) {
      const row = document.createElement("div");
      row.textContent = line || " ";
      block.append(row);
    }
    return block;
  }

  ignoreEvent(): boolean {
    return true;
  }
}
