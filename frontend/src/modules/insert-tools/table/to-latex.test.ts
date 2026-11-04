import { describe, expect, it } from "vitest";

import { escapeLatex, labelFor, safeWidth, tableToLatex } from "./to-latex";
import { emptyTable, setCell, type TableDraft } from "./table-model";

/** A draft with the given cells, one left-aligned column per cell of the first row. */
function draftOf(cells: string[][], overrides: Partial<TableDraft> = {}): TableDraft {
  const base = emptyTable(cells.length, cells[0]!.length);
  return { ...base, cells, header: false, label: "", placement: "", ...overrides };
}

describe("escapeLatex", () => {
  it("escapes every special character once", () => {
    expect(escapeLatex("a & b % $5 #1 _x_ {y} ~ ^ \\")).toBe(
      "a \\& b \\% \\$5 \\#1 \\_x\\_ \\{y\\} \\textasciitilde{} \\textasciicircum{} \\textbackslash{}",
    );
  });

  it("turns 50% into 50\\%, as the acceptance criteria require", () => {
    expect(escapeLatex("50%")).toBe("50\\%");
  });

  it("leaves plain text alone", () => {
    expect(escapeLatex("Mean (SD)")).toBe("Mean (SD)");
  });
});

describe("tableToLatex", () => {
  it("writes a booktabs table with a header, a caption and a label", () => {
    const draft = draftOf(
      [
        ["a", "b"],
        ["c", "d"],
      ],
      {
        header: true,
        caption: "Results",
        label: "tab:results",
        placement: "htbp",
        columns: [
          { align: "l", width: "3cm" },
          { align: "r", width: "3cm" },
        ],
      },
    );
    expect(tableToLatex(draft)).toBe(
      [
        "\\begin{table}[htbp]",
        "  \\centering",
        "  \\caption{Results}",
        "  \\label{tab:results}",
        "  \\begin{tabular}{lr}",
        "    \\toprule",
        "    a & b \\\\",
        "    \\midrule",
        "    c & d \\\\",
        "    \\bottomrule",
        "  \\end{tabular}",
        "\\end{table}",
      ].join("\n"),
    );
  });

  it("writes no midrule without a header row", () => {
    const code = tableToLatex(draftOf([["a"]], { style: "booktabs", header: false }));
    expect(code).not.toContain("\\midrule");
    expect(code).toContain("\\toprule");
    expect(code).toContain("\\bottomrule");
  });

  it("writes a grid with vertical bars and a rule under every row", () => {
    const code = tableToLatex(
      draftOf(
        [
          ["a", "b"],
          ["c", "d"],
        ],
        {
          style: "grid",
          columns: [
            { align: "l", width: "3cm" },
            { align: "c", width: "3cm" },
          ],
        },
      ),
    );
    expect(code).toContain("\\begin{tabular}{|l|c|}");
    expect(code.split("\\hline")).toHaveLength(4);
    expect(code).not.toContain("\\toprule");
  });

  it("writes a paragraph column with its width", () => {
    const code = tableToLatex(draftOf([["text"]], { columns: [{ align: "p", width: "4.5cm" }] }));
    expect(code).toContain("\\begin{tabular}{p{4.5cm}}");
  });

  it("falls back to the default width when the width is not a dimension", () => {
    expect(safeWidth("3 furlongs")).toBe("3cm");
    expect(safeWidth(" 2.5in ")).toBe("2.5in");
    expect(safeWidth("0.4\\textwidth")).toBe("0.4\\textwidth");
  });

  it("escapes cell text unless the cells are marked as LaTeX", () => {
    const plain = tableToLatex(draftOf([["50%"]]));
    expect(plain).toContain("    50\\% \\\\");
    const latex = tableToLatex(draftOf([["$x^2$"]], { cellsAreLatex: true }));
    expect(latex).toContain("    $x^2$ \\\\");
  });

  it("escapes the caption too, and writes no caption or label when they are empty", () => {
    const code = tableToLatex(draftOf([["a"]], { caption: "Costs (50%)" }));
    expect(code).toContain("\\caption{Costs (50\\%)}");
    expect(code).not.toContain("\\label");
    expect(tableToLatex(draftOf([["a"]]))).not.toContain("\\caption");
  });

  it("joins a cell's line breaks into one line", () => {
    expect(tableToLatex(draftOf([["one\ntwo"]]))).toContain("one two \\\\");
  });

  it("omits the placement brackets when there is none", () => {
    expect(tableToLatex(draftOf([["a"]], { placement: "  " }))).toMatch(/^\\begin\{table\}\n/);
  });

  it("builds a fresh 3 by 3 draft that compiles to a 3 by 3 tabular", () => {
    const code = tableToLatex(emptyTable());
    expect(code.match(/\\\\/g)).toHaveLength(3);
    expect(code).toContain("\\begin{tabular}{lll}");
  });

  it("uses the edited cell text", () => {
    const draft = setCell(emptyTable(1, 1), 0, 0, "Mean");
    expect(tableToLatex({ ...draft, header: false })).toContain("    Mean \\\\");
  });
});

describe("labelFor", () => {
  it("suggests tab: and the caption's words, without accents", () => {
    expect(labelFor("Résumé dos dados!")).toBe("tab:resume-dos-dados");
    expect(labelFor("")).toBe("tab:");
  });
});
