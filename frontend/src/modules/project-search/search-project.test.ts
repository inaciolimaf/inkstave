import { describe, expect, it } from "vitest";

import { searchSources } from "./search-project";

const sources = [
  { id: "m", path: "main.tex", text: "\\input{intro}\nneural network\n" },
  { id: "i", path: "chapters/intro.tex", text: "A neural network.\nAnother neural net.\n" },
  { id: "b", path: "refs.bib", text: "@article{x, title={Nothing}}" },
];

describe("searchSources", () => {
  it("groups the matches by file, in path order, and leaves out files without one", () => {
    const results = searchSources(sources, /neural/g);
    expect(results.files.map((f) => [f.path, f.matches.length])).toEqual([
      ["chapters/intro.tex", 2],
      ["main.tex", 1],
    ]);
    expect(results.total).toBe(3);
    expect(results.truncated).toBe(false);
  });

  it("says when the cap cut the list", () => {
    const results = searchSources(sources, /neural/g, 2);
    expect(results.total).toBe(2);
    expect(results.truncated).toBe(true);
    expect(results.files.map((f) => f.path)).toEqual(["chapters/intro.tex"]);
  });

  it("is not truncated when the cap is met exactly", () => {
    expect(searchSources(sources, /neural/g, 3).truncated).toBe(false);
  });
});
