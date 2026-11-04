import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { makeView } from "../test-view";

import { TableBuilder } from "./table-builder";

const PLAIN = "\\documentclass{article}\n\\begin{document}\n\n\\end{document}\n";

function cell(row: number, column: number) {
  return screen.getByRole("textbox", { name: `Row ${row}, column ${column}` });
}

describe("TableBuilder", () => {
  it("starts from a 3 by 3 grid and inserts a booktabs table with a header at the cursor", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const view = makeView(PLAIN, PLAIN.indexOf("\n\\end"));
    render(<TableBuilder view={view} mainText={PLAIN} onClose={onClose} />);
    expect(screen.getAllByRole("textbox", { name: /^Row \d+, column \d+$/ })).toHaveLength(9);
    await user.type(cell(1, 1), "Name");
    await user.click(screen.getByRole("button", { name: "Insert table" }));
    const text = view.state.doc.toString();
    expect(text).toContain("\\begin{table}[htbp]");
    expect(text).toContain("\\toprule");
    expect(text).toContain("Name & ");
    expect(text).toContain("\\midrule");
    expect(onClose).toHaveBeenCalled();
  });

  it("fills the grid from a pasted 4 by 3 spreadsheet block and grows it", async () => {
    const user = userEvent.setup();
    const view = makeView(PLAIN, PLAIN.indexOf("\n\\end"));
    render(<TableBuilder view={view} mainText={PLAIN} onClose={vi.fn()} />);
    const target = cell(1, 1);
    target.focus();
    const sheet = "a\tb\tc\nd\te\tf\ng\th\ti\nj\tk\tl";
    await user.paste(sheet);
    expect(cell(4, 1)).toHaveValue("j");
    expect(cell(4, 3)).toHaveValue("l");
    expect(cell(2, 2)).toHaveValue("e");
    await user.click(screen.getByRole("button", { name: "Insert table" }));
    expect(view.state.doc.toString()).toContain("g & h & i \\\\");
  });

  it("pastes a single cell as ordinary text", async () => {
    const user = userEvent.setup();
    render(<TableBuilder view={makeView(PLAIN)} mainText={PLAIN} onClose={vi.fn()} />);
    await user.click(cell(1, 1));
    await user.paste("plain");
    expect(cell(1, 1)).toHaveValue("plain");
    expect(screen.getAllByRole("textbox", { name: /^Row \d+, column \d+$/ })).toHaveLength(9);
  });

  it("escapes a cell that holds a percent sign", async () => {
    const user = userEvent.setup();
    const view = makeView(PLAIN);
    render(<TableBuilder view={view} mainText={PLAIN} onClose={vi.fn()} />);
    await user.type(cell(1, 1), "50%");
    await user.click(screen.getByRole("button", { name: "Insert table" }));
    expect(view.state.doc.toString()).toContain("50\\%");
  });

  it("keeps cell LaTeX when the person marks the cells as LaTeX", async () => {
    const user = userEvent.setup();
    const view = makeView(PLAIN);
    render(<TableBuilder view={view} mainText={PLAIN} onClose={vi.fn()} />);
    await user.click(screen.getByRole("checkbox", { name: "Cells contain LaTeX" }));
    await user.type(cell(1, 1), "$x^2$");
    await user.click(screen.getByRole("button", { name: "Insert table" }));
    expect(view.state.doc.toString()).toContain("$x^2$");
  });

  it("writes the label from the caption until the label is typed by hand", async () => {
    const user = userEvent.setup();
    render(<TableBuilder view={makeView(PLAIN)} mainText={PLAIN} onClose={vi.fn()} />);
    const label = screen.getByRole("textbox", { name: "Label" });
    await user.type(screen.getByRole("textbox", { name: "Caption" }), "Test results");
    expect(label).toHaveValue("tab:test-results");
    await user.clear(label);
    await user.type(label, "tab:mine");
    await user.type(screen.getByRole("textbox", { name: "Caption" }), "!");
    expect(label).toHaveValue("tab:mine");
  });

  it("switches to a grid with vertical rules and offers no package", async () => {
    const user = userEvent.setup();
    const view = makeView(PLAIN);
    render(<TableBuilder view={view} mainText={PLAIN} onClose={vi.fn()} />);
    await user.selectOptions(screen.getByRole("combobox", { name: "Rules" }), "grid");
    expect(screen.queryByRole("status")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Insert table" }));
    expect(view.state.doc.toString()).toContain("\\begin{tabular}{|l|l|l|}");
    expect(view.state.doc.toString()).toContain("\\hline");
  });

  it("asks for booktabs when the main document does not load it", () => {
    render(<TableBuilder view={makeView(PLAIN)} mainText={PLAIN} onClose={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Needs \\usepackage{booktabs}");
  });

  it("adds and removes rows and columns from the grid", async () => {
    const user = userEvent.setup();
    render(<TableBuilder view={makeView(PLAIN)} mainText={PLAIN} onClose={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Add row" }));
    await user.click(screen.getByRole("button", { name: "Add column" }));
    expect(screen.getAllByRole("textbox", { name: /^Row \d+, column \d+$/ })).toHaveLength(16);
    await user.click(screen.getByRole("button", { name: "Remove row 1" }));
    expect(screen.getAllByRole("textbox", { name: /^Row \d+, column \d+$/ })).toHaveLength(12);
  });

  it("gives a paragraph column its width, and writes it into the column spec", async () => {
    const user = userEvent.setup();
    const view = makeView(PLAIN);
    render(<TableBuilder view={view} mainText={PLAIN} onClose={vi.fn()} />);
    const align = screen.getByRole("combobox", { name: "Alignment of column 1" });
    await user.selectOptions(align, "p");
    await user.clear(screen.getByRole("textbox", { name: "Width of column 1" }));
    await user.type(screen.getByRole("textbox", { name: "Width of column 1" }), "4cm");
    await user.click(screen.getByRole("button", { name: "Insert table" }));
    expect(view.state.doc.toString()).toContain("\\begin{tabular}{p{4cm}ll}");
  });

  it("leaves the document alone on Cancel", async () => {
    const user = userEvent.setup();
    const view = makeView(PLAIN);
    const onClose = vi.fn();
    render(<TableBuilder view={view} mainText={PLAIN} onClose={onClose} />);
    await user.click(cell(1, 1));
    await user.type(cell(1, 1), "unused");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(view.state.doc.toString()).toBe(PLAIN);
    expect(onClose).toHaveBeenCalled();
  });
});
