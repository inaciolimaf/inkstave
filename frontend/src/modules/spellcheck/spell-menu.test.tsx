import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SpellMenu, type SpellMenuState } from "./spell-menu";
import type { SpellcheckBinding } from "./types";

function binding(suggestions: string[]): SpellcheckBinding {
  return {
    language: "en-US",
    checker: {
      check: vi.fn(async () => []),
      suggest: vi.fn(async () => suggestions),
    },
    accepts: () => false,
    addToDictionary: vi.fn(),
    ignoreInDocument: vi.fn(),
    reportFailure: vi.fn(),
  };
}

function editorWith(doc: string): EditorView {
  const parent = document.createElement("div");
  document.body.append(parent);
  return new EditorView({ state: EditorState.create({ doc }), parent });
}

const state: SpellMenuState = { from: 2, to: 5, word: "teh", x: 10, y: 20 };

describe("SpellMenu", () => {
  it("offers the suggestions, then the dictionary and ignore actions", async () => {
    const spell = binding(["the", "ten"]);
    render(<SpellMenu state={state} view={null} binding={spell} onClose={vi.fn()} />);
    expect(await screen.findByRole("menuitem", { name: "the" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "ten" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Add to dictionary" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Ignore in this document" })).toBeTruthy();
    expect(spell.checker.suggest).toHaveBeenCalledWith("en-US", "teh");
  });

  it("says so when there are no suggestions", async () => {
    render(<SpellMenu state={state} view={null} binding={binding([])} onClose={vi.fn()} />);
    expect(await screen.findByText("No suggestions")).toBeTruthy();
  });

  it("replaces the word with the chosen suggestion and closes", async () => {
    const view = editorWith("a teh b");
    const onClose = vi.fn();
    render(<SpellMenu state={state} view={view} binding={binding(["the"])} onClose={onClose} />);
    await userEvent.click(await screen.findByRole("menuitem", { name: "the" }));
    expect(view.state.doc.toString()).toBe("a the b");
    expect(onClose).toHaveBeenCalled();
  });

  it("leaves the text alone when it changed since the menu opened", async () => {
    const view = editorWith("a cat b");
    render(<SpellMenu state={state} view={view} binding={binding(["the"])} onClose={vi.fn()} />);
    await userEvent.click(await screen.findByRole("menuitem", { name: "the" }));
    expect(view.state.doc.toString()).toBe("a cat b");
  });

  it("adds the word to the personal dictionary", async () => {
    const spell = binding([]);
    const onClose = vi.fn();
    render(<SpellMenu state={state} view={null} binding={spell} onClose={onClose} />);
    await userEvent.click(await screen.findByRole("menuitem", { name: "Add to dictionary" }));
    expect(spell.addToDictionary).toHaveBeenCalledWith("teh");
    expect(onClose).toHaveBeenCalled();
  });

  it("ignores the word in this document", async () => {
    const spell = binding([]);
    render(<SpellMenu state={state} view={null} binding={spell} onClose={vi.fn()} />);
    await userEvent.click(await screen.findByRole("menuitem", { name: "Ignore in this document" }));
    await waitFor(() => expect(spell.ignoreInDocument).toHaveBeenCalledWith("teh"));
  });
});
