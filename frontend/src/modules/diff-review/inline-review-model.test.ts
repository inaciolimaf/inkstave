import { describe, expect, it } from "vitest";

import { displayLine, nextOpen, outcomeLists, type ReviewHunk } from "./inline-review-model";
import type { DiffHunk, LineType } from "./types";

function hunk(id: string, oldStart: number, lines: [LineType, string][]): DiffHunk {
  return {
    id,
    header: `@@ -${oldStart} @@`,
    oldStart,
    oldLines: lines.filter(([t]) => t !== "add").length,
    newStart: oldStart,
    newLines: lines.filter(([t]) => t !== "del").length,
    lines: lines.map(([type, text]) => ({ type, text })),
  };
}

const REPLACE_B = hunk("h1", 2, [
  ["del", "b"],
  ["add", "B"],
]);

function review(id: string, decision: ReviewHunk["decision"]): ReviewHunk {
  return { hunk: hunk(id, 1, []), decision, blocked: false, busy: false, line: 0 };
}

describe("displayLine", () => {
  it("finds the hunk where its old lines are", () => {
    expect(displayLine(["a", "b", "c"], REPLACE_B, 0)).toEqual({ line: 1, blocked: false });
  });

  it("draws a blocked hunk at the line the proposal names, clamped to the text", () => {
    expect(displayLine(["a", "DIFFERENT", "c"], REPLACE_B, 1)).toEqual({ line: 1, blocked: true });
    expect(displayLine(["a"], REPLACE_B, 9)).toEqual({ line: 0, blocked: true });
  });

  it("places a pure insertion at the hint, never past the last line", () => {
    const insert = hunk("h2", 3, [["add", "new"]]);
    expect(displayLine(["a", "b"], insert, 5)).toEqual({ line: 1, blocked: false });
  });
});

describe("outcomeLists", () => {
  it("lists every decided hunk once, in the list of its decision", () => {
    const hunks = [review("h1", "accepted"), review("h2", "rejected"), review("h3", "stale")];
    expect(outcomeLists(hunks)).toEqual({ accepted: ["h1"], rejected: ["h2"], stale: ["h3"] });
  });

  it("leaves an open hunk out, so the caller can tell the review is not finished", () => {
    expect(outcomeLists([review("h1", "open")])).toEqual({ accepted: [], rejected: [], stale: [] });
  });
});

describe("nextOpen", () => {
  it("skips decided hunks and wraps around", () => {
    const hunks = [review("h1", "accepted"), review("h2", "open"), review("h3", "open")];
    expect(nextOpen(hunks, 0)).toBe(1);
    expect(nextOpen(hunks, 2)).toBe(2);
  });

  it("stays where it is when nothing is open", () => {
    expect(nextOpen([review("h1", "rejected")], 0)).toBe(0);
  });
});
