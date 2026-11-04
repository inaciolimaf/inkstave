import { describe, expect, it } from "vitest";

import { findMatches } from "./find";
import { applyEdits, expandReplacement, relocate, replacementEdits } from "./replace";

const [refMatch] = findMatches("\\ref{fig:x}", /\\ref\{(?<key>fig):(x)\}/g);

describe("expandReplacement", () => {
  it("writes a plain replacement as typed, $ included", () => {
    expect(expandReplacement("$1 costs $&", refMatch, false)).toBe("$1 costs $&");
  });

  it.each([
    ["$1-$2", "fig-x"],
    ["$&!", "\\ref{fig:x}!"],
    ["$<key>", "fig"],
    ["$$1", "$1"],
    ["$9", "$9"],
    ["$<none>", "$<none>"],
    ["$12", "fig2"],
  ])("expands %s in a regular expression", (template, expected) => {
    expect(expandReplacement(template, refMatch, true)).toBe(expected);
  });
});

describe("replacing", () => {
  it("renames a label and every reference to it", () => {
    const text = "\\label{fig:x}\nSee \\ref{fig:x} and \\ref{fig:xy}.";
    const pattern = /\\(label|ref)\{fig:x\}/g;
    const edits = replacementEdits(findMatches(text, pattern), "\\$1{fig:result}", true);
    expect(applyEdits(text, edits)).toBe("\\label{fig:result}\nSee \\ref{fig:result} and \\ref{fig:xy}.");
  });

  it("applies edits in any order", () => {
    const edits = [
      { from: 4, to: 5, insert: "B" },
      { from: 0, to: 1, insert: "A" },
    ];
    expect(applyEdits("a - b", edits)).toBe("A - B");
  });
});

describe("relocate", () => {
  it("finds the same match after the text above it moved", () => {
    const before = findMatches("one\ntwo net\n", /net/g)[0];
    const now = findMatches("zero\none\ntwo net\n", /net/g);
    expect(relocate(now, before)?.from).toBe(now[0].from);
  });

  it("refuses a match whose line changed", () => {
    const before = findMatches("two net\n", /net/g)[0];
    expect(relocate(findMatches("two nets net\n", /net/g), before)).toBeNull();
  });
});
