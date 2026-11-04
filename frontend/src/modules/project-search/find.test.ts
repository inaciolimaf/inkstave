import { describe, expect, it } from "vitest";

import { findMatches, previewOf } from "./find";

describe("findMatches", () => {
  it("gives the line, column and offsets of each match", () => {
    const text = "first line\nsecond net\nnet net";
    const matches = findMatches(text, /net/g);
    expect(matches.map((m) => [m.line, m.column, m.from])).toEqual([
      [2, 7, 18],
      [3, 0, 22],
      [3, 4, 26],
    ]);
    expect(matches[0].lineText).toBe("second net");
    expect(text.slice(matches[2].from, matches[2].to)).toBe("net");
  });

  it("skips empty matches and never loops on them", () => {
    expect(findMatches("abc", /x*/g)).toEqual([]);
    expect(findMatches("aXa", /X?/g).map((m) => m.text)).toEqual(["X"]);
  });

  it("stops at the limit", () => {
    expect(findMatches("a a a a", /a/g, 2)).toHaveLength(2);
  });

  it("keeps capture groups for the replacement", () => {
    const [match] = findMatches("\\ref{fig:one}", /\\ref\{(?<key>[^}]+)\}/g);
    expect(match.groups).toEqual(["fig:one"]);
    expect(match.named).toEqual({ key: "fig:one" });
  });

  it("counts offsets in UTF-16 units, as Yjs does", () => {
    const [match] = findMatches("😀 é net", /net/g);
    expect(match.from).toBe("😀 é ".length);
  });
});

describe("previewOf", () => {
  it("cuts a long line around the match", () => {
    const line = `${"x".repeat(100)} target ${"y".repeat(200)}`;
    const [match] = findMatches(line, /target/g);
    const preview = previewOf(match);
    expect(preview.before.startsWith("…")).toBe(true);
    expect(preview.match).toBe("target");
    expect(preview.after.length).toBeLessThanOrEqual(80);
  });
});
