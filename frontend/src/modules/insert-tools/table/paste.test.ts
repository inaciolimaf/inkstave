import { describe, expect, it } from "vitest";

import { isGridText, parseGridText } from "./paste";
import {
  addColumn,
  addRow,
  emptyTable,
  MAX_COLUMNS,
  MAX_ROWS,
  pasteGrid,
  removeRow,
  setCell,
} from "./table-model";

describe("parseGridText", () => {
  it("splits tab-separated rows, as a spreadsheet copies them", () => {
    expect(parseGridText("a\tb\n1\t2\n")).toEqual([
      ["a", "b"],
      ["1", "2"],
    ]);
  });

  it("accepts Windows line endings and drops trailing empty rows", () => {
    expect(parseGridText("a\tb\r\n1\t2\r\n\r\n")).toEqual([
      ["a", "b"],
      ["1", "2"],
    ]);
  });

  it("keeps a quoted cell with a line break and a tab in one cell", () => {
    expect(parseGridText('"first\nsecond"\tx\ny\tz')).toEqual([
      ["first\nsecond", "x"],
      ["y", "z"],
    ]);
  });

  it("reads doubled quotes inside a quoted cell as one quote", () => {
    expect(parseGridText('"say ""hi"""\tnext')).toEqual([['say "hi"', "next"]]);
  });

  it("keeps empty cells in place", () => {
    expect(parseGridText("a\t\tc")).toEqual([["a", "", "c"]]);
  });
});

describe("isGridText", () => {
  it("is true for tab or line separated text", () => {
    expect(isGridText("a\tb")).toBe(true);
    expect(isGridText("a\nb")).toBe(true);
  });

  it("is false for one line of plain text, even with a final newline", () => {
    expect(isGridText("hello")).toBe(false);
    expect(isGridText("hello\n")).toBe(false);
  });
});

describe("table model", () => {
  it("starts from a 3 by 3 grid with a header row", () => {
    const draft = emptyTable();
    expect(draft.cells).toHaveLength(3);
    expect(draft.columns).toHaveLength(3);
    expect(draft.header).toBe(true);
  });

  it("adds and removes rows and columns, never below one", () => {
    let draft = emptyTable(1, 1);
    draft = removeRow(draft, 0);
    expect(draft.cells).toHaveLength(1);
    draft = addRow(addColumn(draft));
    expect(draft.cells).toHaveLength(2);
    expect(draft.cells[1]).toHaveLength(2);
  });

  it("stops at 30 rows and 15 columns", () => {
    let draft = emptyTable(1, 1);
    for (let i = 0; i < 40; i++) draft = addRow(addColumn(draft));
    expect(draft.cells).toHaveLength(MAX_ROWS);
    expect(draft.columns).toHaveLength(MAX_COLUMNS);
  });

  it("writes setCell without touching the other cells", () => {
    const draft = setCell(emptyTable(2, 2), 1, 0, "x");
    expect(draft.cells).toEqual([
      ["", ""],
      ["x", ""],
    ]);
  });

  it("fills a 4 by 3 block from a cell and grows the grid to fit", () => {
    const block = [
      ["a", "b", "c"],
      ["d", "e", "f"],
      ["g", "h", "i"],
      ["j", "k", "l"],
    ];
    const draft = pasteGrid(emptyTable(), 0, 0, block);
    expect(draft.cells).toEqual(block);
  });

  it("starts the paste at the focused cell, and keeps the cells before it", () => {
    const draft = pasteGrid(setCell(emptyTable(), 0, 0, "keep"), 1, 1, [["x", "y"]]);
    expect(draft.cells[0]?.[0]).toBe("keep");
    expect(draft.cells[1]).toEqual(["", "x", "y"]);
  });
});
