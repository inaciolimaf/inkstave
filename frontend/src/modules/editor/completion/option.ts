import { type Completion, insertCompletionText, snippet } from "@codemirror/autocomplete";
import type { EditorView } from "@codemirror/view";

/** The `apply` of a completion: what replaces the typed prefix `from`..`to`. */
export type Apply = (view: EditorView, completion: Completion, from: number, to: number) => void;

/** Completions accepted in this editor. The ones used before rank first among equal matches (spec 112). */
export class RecentUses {
  private readonly used = new Set<string>();

  record(key: string): void {
    this.used.add(key);
  }

  boost(key: string): number {
    return this.used.has(key) ? 1 : 0;
  }
}

/** Plain text, inserted in place of the typed prefix. */
export function insertText(text: string): Apply {
  return (view, _completion, from, to) => view.dispatch(insertCompletionText(view.state, text, from, to));
}

/** A snippet with fields (`${}` is a field, Tab moves between them, Escape leaves them). */
export function insertSnippet(template: string): Apply {
  return snippet(template);
}

export interface OptionSpec {
  /** Identifies the completion for the recency rank, e.g. `cmd:section`. */
  key: string;
  label: string;
  apply: string | Apply;
  detail?: string;
  info?: string;
  type?: string;
}

/** A completion whose acceptance is recorded, so the next list puts it first among equal matches. */
export function toOption(recent: RecentUses, spec: OptionSpec): Completion {
  const apply = typeof spec.apply === "string" ? insertText(spec.apply) : spec.apply;
  return {
    label: spec.label,
    detail: spec.detail,
    info: spec.info,
    type: spec.type,
    boost: recent.boost(spec.key),
    apply: (view, completion, from, to) => {
      recent.record(spec.key);
      apply(view, completion, from, to);
    },
  };
}
