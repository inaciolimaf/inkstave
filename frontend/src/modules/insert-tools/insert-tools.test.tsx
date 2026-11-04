import { undo } from "@codemirror/commands";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { InsertMenu } from "./insert-menu";
import { makeView } from "./test-view";

vi.mock("./equation/mathlive-loader", () => ({ loadMathLive: vi.fn(() => Promise.resolve()) }));

const PLAIN = "\\documentclass{article}\n\\begin{document}\n\n\\end{document}\n";

function renderMenu(view: ReturnType<typeof makeView>, readOnly = false) {
  return render(<InsertMenu view={view} readOnly={readOnly} mainText={PLAIN} />);
}

async function openMenuItem(name: string) {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Insert" }));
  await user.click(screen.getByRole("menuitem", { name }));
  return user;
}

describe("InsertMenu", () => {
  it("offers symbols, a table and an equation", async () => {
    renderMenu(makeView(""));
    await userEvent.setup().click(screen.getByRole("button", { name: "Insert" }));
    expect(screen.getByRole("menuitem", { name: "Symbol…" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Table…" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Equation…" })).toBeInTheDocument();
  });

  it("cannot be opened by a viewer", () => {
    renderMenu(makeView(""), true);
    expect(screen.getByRole("button", { name: "Insert" })).toBeDisabled();
  });

  it("opens the symbol palette from the menu", async () => {
    renderMenu(makeView(""));
    await openMenuItem("Symbol…");
    expect(screen.getByRole("searchbox", { name: "Search symbols" })).toBeInTheDocument();
  });

  it("opens the table builder from the menu", async () => {
    renderMenu(makeView(""));
    await openMenuItem("Table…");
    expect(screen.getByRole("dialog", { name: "Table" })).toBeInTheDocument();
  });

  it("opens the equation editor from the menu", async () => {
    renderMenu(makeView(""));
    await openMenuItem("Equation…");
    expect(screen.getByRole("dialog", { name: "Equation" })).toBeInTheDocument();
  });

  it("opens the palette on Ctrl+Shift+Y", () => {
    renderMenu(makeView(""));
    fireEvent.keyDown(window, { key: "Y", ctrlKey: true, shiftKey: true });
    expect(screen.getByRole("searchbox", { name: "Search symbols" })).toBeInTheDocument();
  });

  it("opens the equation editor on Cmd+Shift+E", async () => {
    renderMenu(makeView(""));
    fireEvent.keyDown(window, { key: "E", metaKey: true, shiftKey: true });
    expect(screen.getByRole("dialog", { name: "Equation" })).toBeInTheDocument();
    await waitFor(() => expect(document.querySelector("math-field")).not.toBeNull());
  });

  it("ignores the shortcuts for a viewer", () => {
    renderMenu(makeView(""), true);
    fireEvent.keyDown(window, { key: "Y", ctrlKey: true, shiftKey: true });
    expect(screen.queryByRole("searchbox", { name: "Search symbols" })).toBeNull();
  });
});

describe("insert tools are one undoable edit each", () => {
  it("takes back only the symbol, not the typing before it", async () => {
    const view = makeView("Hello ", 6);
    renderMenu(view);
    view.dispatch({ changes: { from: 6, insert: "x" }, selection: { anchor: 7 } });
    fireEvent.keyDown(window, { key: "Y", ctrlKey: true, shiftKey: true });
    await userEvent.setup().click(screen.getByRole("button", { name: "\\alpha" }));
    expect(view.state.doc.toString()).toBe("Hello x\\alpha");
    undo(view);
    expect(view.state.doc.toString()).toBe("Hello x");
  });

  it("takes back one table in one Undo", async () => {
    const view = makeView(PLAIN, PLAIN.indexOf("\n\\end"));
    const before = view.state.doc.toString();
    renderMenu(view);
    const user = await openMenuItem("Table…");
    await user.click(screen.getByRole("button", { name: "Insert table" }));
    expect(view.state.doc.toString()).not.toBe(before);
    undo(view);
    expect(view.state.doc.toString()).toBe(before);
  });

  it("takes back one equation in one Undo", async () => {
    const view = makeView("Text ", 5);
    renderMenu(view);
    const user = await openMenuItem("Equation…");
    await waitFor(() => expect(document.querySelector("math-field")).not.toBeNull());
    const field = document.querySelector("math-field") as HTMLElement & { value: string };
    act(() => {
      field.value = "\\alpha";
      field.dispatchEvent(new Event("input"));
    });
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(view.state.doc.toString()).toBe("Text \\(\\alpha\\)");
    undo(view);
    expect(view.state.doc.toString()).toBe("Text ");
  });
});
