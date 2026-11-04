import { Compartment, EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { misspelledAt, spellcheckExtension, type SpellcheckOptions } from "./spellcheck-extension";
import type { DictionaryLanguage, SpellChecker } from "./types";

/** A checker that knows everything except the given words. No dictionary is loaded. */
function fakeChecker(misspelled: string[]) {
  const check = vi.fn(async (_language: DictionaryLanguage, words: string[]) =>
    words.filter((word) => misspelled.includes(word)),
  );
  const suggest = vi.fn(async () => ["the"]);
  const checker: SpellChecker = { check, suggest };
  return { checker, check, suggest };
}

function options(overrides: Partial<SpellcheckOptions> & { checker: SpellChecker }): SpellcheckOptions {
  return { language: "en-US", accepts: () => false, ...overrides };
}

const mounted: EditorView[] = [];

function mount(
  doc: string,
  extension: ReturnType<typeof spellcheckExtension> | ReturnType<Compartment["of"]>,
) {
  const parent = document.createElement("div");
  document.body.append(parent);
  const view = new EditorView({ state: EditorState.create({ doc, extensions: [extension] }), parent });
  mounted.push(view);
  return view;
}

/** The debounce is 400 ms; advancing past it also lets the worker answer (a resolved promise). */
async function settle(): Promise<void> {
  await vi.advanceTimersByTimeAsync(400);
}

function marked(view: EditorView): string[] {
  return [...view.contentDOM.querySelectorAll(".cm-misspelled")].map((node) => node.textContent ?? "");
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  for (const view of mounted.splice(0)) view.destroy();
  document.body.replaceChildren();
  vi.useRealTimers();
});

describe("spellcheck extension", () => {
  it("underlines the misspelled words of the text", async () => {
    const { checker } = fakeChecker(["teh"]);
    const view = mount("This is teh text.", spellcheckExtension(options({ checker })));
    await settle();
    expect(marked(view)).toEqual(["teh"]);
  });

  it("waits for the debounce before it checks", async () => {
    const { checker, check } = fakeChecker(["teh"]);
    mount("teh", spellcheckExtension(options({ checker })));
    await vi.advanceTimersByTimeAsync(399);
    expect(check).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(check).toHaveBeenCalledTimes(1);
  });

  it("asks the worker only about checkable words", async () => {
    const { checker, check } = fakeChecker([]);
    mount("\\documentclass{artcle} $\\alpha$ teh % wrold", spellcheckExtension(options({ checker })));
    await settle();
    expect(check).toHaveBeenCalledWith("en-US", ["teh"]);
  });

  it("does not mark words the personal dictionary or the ignore list accept", async () => {
    const { checker } = fakeChecker(["teh", "wrold"]);
    const view = mount("teh wrold", spellcheckExtension(options({ checker, accepts: (w) => w === "teh" })));
    await settle();
    expect(marked(view)).toEqual(["wrold"]);
  });

  it("removes an underline when the word becomes accepted, without asking again", async () => {
    const { checker, check } = fakeChecker(["teh"]);
    const config = new Compartment();
    const view = mount("teh", config.of(spellcheckExtension(options({ checker }))));
    await settle();
    expect(marked(view)).toEqual(["teh"]);
    view.dispatch({
      effects: config.reconfigure(spellcheckExtension(options({ checker, accepts: (w) => w === "teh" }))),
    });
    await settle();
    expect(marked(view)).toEqual([]);
    expect(check).toHaveBeenCalledTimes(1);
  });

  it("checks again after a language switch", async () => {
    const { checker, check } = fakeChecker(["metodolgia"]);
    const config = new Compartment();
    const view = mount("metodolgia", config.of(spellcheckExtension(options({ checker }))));
    await settle();
    expect(check).toHaveBeenLastCalledWith("en-US", ["metodolgia"]);

    view.dispatch({
      effects: config.reconfigure(spellcheckExtension(options({ checker, language: "pt-BR" }))),
    });
    await settle();
    expect(check).toHaveBeenLastCalledWith("pt-BR", ["metodolgia"]);
    expect(marked(view)).toEqual(["metodolgia"]);
  });

  it("follows the edits: a new misspelled word is underlined after the debounce", async () => {
    const { checker } = fakeChecker(["teh"]);
    const view = mount("start", spellcheckExtension(options({ checker })));
    await settle();
    expect(marked(view)).toEqual([]);
    view.dispatch({ changes: { from: 5, insert: " teh" } });
    await settle();
    expect(marked(view)).toEqual(["teh"]);
  });

  it("keeps the editor working when the dictionary fails to load", async () => {
    const failure = new Error("dictionary request failed");
    const checker: SpellChecker = {
      check: vi.fn(async () => Promise.reject(failure)),
      suggest: vi.fn(async () => []),
    };
    const onFailure = vi.fn();
    const view = mount("teh", spellcheckExtension(options({ checker, onFailure })));
    await settle();
    expect(onFailure).toHaveBeenCalledWith(failure);
    expect(marked(view)).toEqual([]);

    view.dispatch({ changes: { from: 3, insert: " more" } });
    expect(view.state.doc.toString()).toBe("teh more");
  });

  it("reports the misspelled word under a position", async () => {
    const { checker } = fakeChecker(["teh"]);
    const view = mount("a teh b", spellcheckExtension(options({ checker })));
    await settle();
    expect(misspelledAt(view, 3)).toEqual({ from: 2, to: 5, word: "teh" });
    expect(misspelledAt(view, 0)).toBeNull();
  });
});
