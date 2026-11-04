import { describe, expect, it } from "vitest";

import { parseStructure } from "./parse-structure";

describe("parseStructure", () => {
  it.each([
    ["\\part{P}", 0],
    ["\\chapter{C}", 1],
    ["\\section{S}", 2],
    ["\\subsection{S}", 3],
    ["\\subsubsection{S}", 4],
    ["\\paragraph{S}", 5],
    ["\\subparagraph{S}", 6],
  ])("gives %s its level", (source, level) => {
    expect(parseStructure(source)).toEqual([
      { kind: "section", level, title: source.split("{")[1].slice(0, -1), line: 1 },
    ]);
  });

  it("keeps the long title of a sectioning command with a short title", () => {
    expect(parseStructure("\\section[Short]{The Long Title}")).toEqual([
      { kind: "section", level: 2, title: "The Long Title", line: 1 },
    ]);
  });

  it("keeps starred forms as sections", () => {
    expect(parseStructure("\\section*{Unnumbered}")).toEqual([
      { kind: "section", level: 2, title: "Unnumbered", line: 1 },
    ]);
  });

  it("does not split a title on nested braces", () => {
    expect(parseStructure("\\section{A {B} C}")).toEqual([
      { kind: "section", level: 2, title: "A {B} C", line: 1 },
    ]);
  });

  it("reports 1-based line numbers in document order", () => {
    const text = "intro\n\\section{One}\nbody\n\n\\subsection{Two}\n";
    expect(parseStructure(text).map((item) => item.line)).toEqual([2, 5]);
  });

  it("skips a commented-out section", () => {
    expect(parseStructure("% \\section{Old}\n\\section{New}")).toEqual([
      { kind: "section", level: 2, title: "New", line: 2 },
    ]);
  });

  it("keeps a percent sign that is escaped", () => {
    expect(parseStructure("50\\% done \\section{Kept}")).toEqual([
      { kind: "section", level: 2, title: "Kept", line: 1 },
    ]);
  });

  it("skips verbatim-like environments and keeps their line count", () => {
    const text = [
      "\\begin{verbatim}",
      "\\section{Inside}",
      "\\end{verbatim}",
      "\\begin{lstlisting}",
      "\\section{Listed}",
      "\\end{lstlisting}",
      "\\begin{minted}{latex}",
      "\\section{Minted}",
      "\\end{minted}",
      "\\begin{comment}",
      "\\section{Commented}",
      "\\end{comment}",
      "\\section{Real}",
    ].join("\n");
    expect(parseStructure(text)).toEqual([{ kind: "section", level: 2, title: "Real", line: 13 }]);
  });

  it("does not mistake other commands for sections", () => {
    expect(parseStructure("\\sectionmark{x} \\subsectionfoo{y}")).toEqual([]);
  });

  it("collects labels with their names", () => {
    expect(parseStructure("\\section{A}\\label{sec:a}")).toEqual([
      { kind: "section", level: 2, title: "A", line: 1 },
      { kind: "label", title: "sec:a", line: 1 },
    ]);
  });

  it.each([
    ["\\input{chapters/intro}", "chapters/intro"],
    ["\\include{chapters/intro.tex}", "chapters/intro.tex"],
    ["\\subfile{parts/one}", "parts/one"],
  ])("reads the include in %s", (source, target) => {
    expect(parseStructure(source)).toEqual([{ kind: "include", target, line: 1 }]);
  });

  it("joins the directory and the file of \\import", () => {
    expect(parseStructure("\\import{chapters/}{intro}")).toEqual([
      { kind: "include", target: "chapters/intro", line: 1 },
    ]);
  });

  it("does not treat \\includegraphics or \\inputenc as includes", () => {
    expect(parseStructure("\\includegraphics{fig} \\usepackage[utf8]{inputenc}")).toEqual([]);
  });

  it("ignores a command with no argument", () => {
    expect(parseStructure("\\section \\input")).toEqual([]);
  });
});
