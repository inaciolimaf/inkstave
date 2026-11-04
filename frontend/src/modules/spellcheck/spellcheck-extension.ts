/**
 * The CodeMirror side of spell checking (spec 113): a view plugin that checks the visible text, plus the
 * mark decoration that draws the wavy underline and the right-click hook.
 *
 * Only the visible lines and a margin of 50 lines are checked. A check runs 400 ms after the last edit or
 * scroll, in the worker, so typing does not wait for it. Words the user keeps (the personal dictionary and
 * this document's ignore list) are never marked. A failed check stops the plugin and reports the failure;
 * the editor keeps working without underlines.
 */
import { type Extension, Facet, StateEffect } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView, ViewPlugin, type ViewUpdate } from "@codemirror/view";

import { checkableWords } from "./tokenize";
import type { DictionaryLanguage, SpellChecker, SpellcheckBinding } from "./types";

const DEBOUNCE_MS = 400;
const MARGIN_LINES = 50;

export interface MisspelledWord {
  from: number;
  to: number;
  word: string;
}

export interface SpellcheckOptions {
  language: DictionaryLanguage;
  checker: SpellChecker;
  /** True for words the user keeps: the personal dictionary and the document's ignore list. */
  accepts: (word: string) => boolean;
  onFailure?: (error: unknown) => void;
  /** Called on a right click over a misspelled word; the native menu is then suppressed. */
  onContextMenu?: (hit: MisspelledWord, pointer: { x: number; y: number }) => void;
}

/** Options live in a facet, so a reconfiguration is seen by the plugin that is already running. */
const spellOptions = Facet.define<SpellcheckOptions, SpellcheckOptions>({
  combine: (values) => values[0],
});

const spellRefresh = StateEffect.define<null>();
const misspelledMark = Decoration.mark({ class: "cm-misspelled" });

const spellTheme = EditorView.baseTheme({
  ".cm-misspelled": {
    textDecoration: "underline wavy",
    textDecorationColor: "hsl(var(--error-text))",
    textUnderlineOffset: "3px",
  },
});

/** The lines to check: the visible ones and the margin around them, as offsets. */
function checkSpan(view: EditorView): { from: number; to: number } {
  const doc = view.state.doc;
  const ranges = view.visibleRanges;
  if (ranges.length === 0) return { from: 0, to: doc.length };
  const first = doc.lineAt(ranges[0].from).number;
  const last = doc.lineAt(ranges[ranges.length - 1].to).number;
  const startLine = Math.max(1, first - MARGIN_LINES);
  const endLine = Math.min(doc.lines, last + MARGIN_LINES);
  return { from: doc.line(startLine).from, to: doc.line(endLine).to };
}

class SpellChecking {
  decorations: DecorationSet = Decoration.none;
  /** Word to "misspelled?", per plugin instance: a word is asked of the worker once. */
  private readonly verdicts = new Map<string, boolean>();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private stopped = false;
  private language: DictionaryLanguage | null = null;

  constructor(private readonly view: EditorView) {
    this.schedule();
  }

  update(update: ViewUpdate): void {
    if (update.docChanged) this.decorations = this.decorations.map(update.changes);
    const optionsChanged = update.startState.facet(spellOptions) !== update.state.facet(spellOptions);
    if (update.docChanged || update.viewportChanged || optionsChanged) this.schedule();
  }

  destroy(): void {
    this.stopped = true;
    clearTimeout(this.timer);
  }

  private schedule(): void {
    if (this.stopped) return;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.run(), DEBOUNCE_MS);
  }

  private async run(): Promise<void> {
    const options = this.view.state.facet(spellOptions);
    if (this.language !== options.language) {
      // A verdict is about one dictionary: a new language asks again.
      this.verdicts.clear();
      this.language = options.language;
    }
    const doc = this.view.state.doc;
    const span = checkSpan(this.view);
    const words = checkableWords(doc.toString(), span.from, span.to);
    const unknown = [...new Set(words.map((w) => w.word))].filter((w) => !this.verdicts.has(w));
    try {
      await this.ask(options, unknown);
    } catch (error) {
      this.fail(error, options);
      return;
    }
    if (this.stopped || this.view.state.doc !== doc) return; // An edit meanwhile scheduled a new run.
    const marks = words.filter((w) => this.verdicts.get(w.word) && !options.accepts(w.word));
    this.decorations = Decoration.set(marks.map((w) => misspelledMark.range(w.from, w.to)));
    this.view.dispatch({ effects: spellRefresh.of(null) });
  }

  private async ask(options: SpellcheckOptions, unknown: string[]): Promise<void> {
    if (unknown.length === 0) return;
    const misspelled = new Set(await options.checker.check(options.language, unknown));
    for (const word of unknown) this.verdicts.set(word, misspelled.has(word));
  }

  private fail(error: unknown, options: SpellcheckOptions): void {
    this.stopped = true;
    this.decorations = Decoration.none;
    options.onFailure?.(error);
    this.view.dispatch({ effects: spellRefresh.of(null) });
  }
}

const spellPlugin = ViewPlugin.fromClass(SpellChecking, {
  decorations: (plugin) => plugin.decorations,
});

/** The misspelled word that covers `pos`, if any. */
export function misspelledAt(view: EditorView, pos: number): MisspelledWord | null {
  const plugin = view.plugin(spellPlugin);
  if (!plugin) return null;
  let hit: MisspelledWord | null = null;
  plugin.decorations.between(pos, pos, (from, to) => {
    if (hit === null && from <= pos && pos <= to) hit = { from, to, word: view.state.sliceDoc(from, to) };
  });
  return hit;
}

const contextMenuHandler = EditorView.domEventHandlers({
  contextmenu(event, view) {
    const options = view.state.facet(spellOptions);
    const pos = view.posAtCoords({ x: event.clientX, y: event.clientY });
    const hit = pos === null ? null : misspelledAt(view, pos);
    if (!hit || !options.onContextMenu) return false;
    event.preventDefault();
    options.onContextMenu(hit, { x: event.clientX, y: event.clientY });
    return true;
  },
});

/** The whole spell-check configuration. Put it in a compartment and reconfigure it to change anything. */
export function spellcheckExtension(options: SpellcheckOptions): Extension {
  return [spellOptions.of(options), spellPlugin, spellTheme, contextMenuHandler];
}

/** The configuration for one open document, from its binding. */
export function spellcheckFor(
  binding: SpellcheckBinding,
  onContextMenu: (hit: MisspelledWord, pointer: { x: number; y: number }) => void,
): Extension {
  return spellcheckExtension({
    language: binding.language,
    checker: binding.checker,
    accepts: binding.accepts,
    onFailure: binding.reportFailure,
    onContextMenu,
  });
}
