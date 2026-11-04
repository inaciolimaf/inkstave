import { describe, expect, it } from "vitest";

import { findCurrentEntry } from "./current-entry";
import { parseStructure } from "./parse-structure";
import { type IndexedDoc, resolveIncludes } from "./resolve-includes";

function docs(files: Record<string, string>): Map<string, IndexedDoc> {
  return new Map(
    Object.entries(files).map(([path, text]) => [path, { id: path, path, items: parseStructure(text) }]),
  );
}

const sectionsOf = (entries: ReturnType<typeof resolveIncludes>) =>
  entries.map((entry) => `${entry.path}:${entry.line}:${entry.title}`);

describe("resolveIncludes", () => {
  it("places the sections of an included file where the include is", () => {
    const index = docs({
      "main.tex": "\\section{A}\n\\input{chapters/intro}\n\\section{B}",
      "chapters/intro.tex": "\\section{Intro}\n\\subsection{Detail}",
    });
    expect(sectionsOf(resolveIncludes("main.tex", index))).toEqual([
      "main.tex:1:A",
      "chapters/intro.tex:1:Intro",
      "chapters/intro.tex:2:Detail",
      "main.tex:3:B",
    ]);
  });

  it("finds a file named without its extension, and one with it", () => {
    const index = docs({
      "main.tex": "\\include{a}\\input{b.tex}",
      "a.tex": "\\section{A}",
      "b.tex": "\\section{B}",
    });
    expect(sectionsOf(resolveIncludes("main.tex", index))).toEqual(["a.tex:1:A", "b.tex:1:B"]);
  });

  it("resolves \\import against the joined directory", () => {
    const index = docs({
      "main.tex": "\\import{chapters/}{intro}",
      "chapters/intro.tex": "\\section{Intro}",
    });
    expect(sectionsOf(resolveIncludes("main.tex", index))).toEqual(["chapters/intro.tex:1:Intro"]);
  });

  it("skips an include whose file is missing", () => {
    const index = docs({ "main.tex": "\\section{A}\n\\input{gone}" });
    expect(sectionsOf(resolveIncludes("main.tex", index))).toEqual(["main.tex:1:A"]);
  });

  it("renders each file once and stops at a cycle", () => {
    const index = docs({
      "a.tex": "\\section{A}\n\\input{b}",
      "b.tex": "\\section{B}\n\\input{a}",
    });
    expect(sectionsOf(resolveIncludes("a.tex", index))).toEqual(["a.tex:1:A", "b.tex:1:B"]);
  });

  it("renders a file included twice once", () => {
    const index = docs({
      "main.tex": "\\input{x}\n\\input{x}",
      "x.tex": "\\section{X}",
    });
    expect(sectionsOf(resolveIncludes("main.tex", index))).toEqual(["x.tex:1:X"]);
  });

  it("leaves out files the main document does not reach", () => {
    const index = docs({ "main.tex": "\\section{A}", "orphan.tex": "\\section{Orphan}" });
    expect(sectionsOf(resolveIncludes("main.tex", index))).toEqual(["main.tex:1:A"]);
  });

  it("returns nothing when the main document is unknown", () => {
    expect(resolveIncludes(null, docs({ "main.tex": "\\section{A}" }))).toEqual([]);
  });

  it("keeps labels, for the index, next to sections", () => {
    const index = docs({ "main.tex": "\\section{A}\\label{sec:a}" });
    expect(resolveIncludes("main.tex", index).map((entry) => entry.kind)).toEqual(["section", "label"]);
  });
});

describe("findCurrentEntry", () => {
  const entries = resolveIncludes(
    "main.tex",
    docs({
      "main.tex": "\\section{A}\n\\input{c}\n\\section{B}\n\\subsection{B1}",
      "c.tex": "\\section{C}",
    }),
  );

  it("picks the last entry of the open file at or above the cursor", () => {
    expect(findCurrentEntry(entries, "main.tex", 4)).toBe(3);
    expect(findCurrentEntry(entries, "main.tex", 3)).toBe(2);
  });

  it("looks only in the open file", () => {
    expect(findCurrentEntry(entries, "c.tex", 1)).toBe(1);
  });

  it("returns -1 above the first entry or with no file open", () => {
    expect(findCurrentEntry(entries, "main.tex", 0)).toBe(-1);
    expect(findCurrentEntry(entries, null, 4)).toBe(-1);
  });
});
