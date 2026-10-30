import { describe, expect, it } from "vitest";

import { blockedAgainst, minimalEdit, previewContent, rebaseHunks } from "./hunks";
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

const ALL = (...ids: string[]) => new Set(ids);

describe("rebaseHunks", () => {
  it("applies a single replacement", () => {
    const h = hunk("h1", 2, [
      ["del", "b"],
      ["add", "B"],
    ]);
    const r = rebaseHunks("a\nb\nc\n", [h], ALL("h1"));
    expect(r.target).toBe("a\nB\nc\n");
    expect(r.appliedHunkIds).toEqual(["h1"]);
  });

  it("applies multiple non-overlapping hunks without drift", () => {
    const h1 = hunk("h1", 2, [
      ["del", "b"],
      ["add", "B"],
    ]);
    const h2 = hunk("h2", 4, [
      ["del", "d"],
      ["add", "D"],
    ]);
    const r = rebaseHunks("a\nb\nc\nd\ne\n", [h1, h2], ALL("h1", "h2"));
    expect(r.target).toBe("a\nB\nc\nD\ne\n");
  });

  it("handles additions-only and deletions-only", () => {
    const add = hunk("h1", 1, [
      ["ctx", "a"],
      ["add", "x"],
    ]);
    expect(rebaseHunks("a\nb\n", [add], ALL("h1")).target).toBe("a\nx\nb\n");
    const del = hunk("h2", 1, [
      ["ctx", "a"],
      ["del", "b"],
    ]);
    expect(rebaseHunks("a\nb\nc\n", [del], ALL("h2")).target).toBe("a\nc\n");
  });

  it("preserves and omits the trailing newline like the source", () => {
    const h = hunk("h1", 2, [
      ["del", "b"],
      ["add", "B"],
    ]);
    expect(rebaseHunks("a\nb\nc\n", [h], ALL("h1")).target).toBe("a\nB\nc\n");
    expect(rebaseHunks("a\nb\nc", [h], ALL("h1")).target).toBe("a\nB\nc");
  });

  it("excludes rejected hunks (preview)", () => {
    const h1 = hunk("h1", 2, [
      ["del", "b"],
      ["add", "B"],
    ]);
    const h2 = hunk("h2", 3, [
      ["del", "c"],
      ["add", "C"],
    ]);
    expect(previewContent("a\nb\nc\n", [h1, h2], ALL("h1"))).toBe("a\nB\nc\n");
  });
});

describe("base-change detection", () => {
  it("blocks hunks whose old lines no longer match the live content (AC7)", () => {
    const h = hunk("h1", 2, [
      ["del", "b"],
      ["add", "B"],
    ]);
    expect(blockedAgainst("a\nb\nc\n", [h])).toEqual([]); // still applies
    expect(blockedAgainst("a\nDIFFERENT\nc\n", [h])).toEqual(["h1"]); // diverged → blocked
  });

  it("never includes a blocked hunk in the rebased target", () => {
    const ok = hunk("h1", 1, [
      ["del", "a"],
      ["add", "A"],
    ]);
    const gone = hunk("h2", 2, [
      ["del", "b"],
      ["add", "B"],
    ]);
    // live no longer has "b" at that location
    const r = rebaseHunks("a\nZZZ\nc\n", [ok, gone], ALL("h1", "h2"));
    expect(r.appliedHunkIds).toEqual(["h1"]);
    expect(r.blockedHunkIds).toEqual(["h2"]);
    expect(r.target).toBe("A\nZZZ\nc\n");
  });
});

describe("minimalEdit", () => {
  it("produces a small region edit, not a full replace", () => {
    const edit = minimalEdit("aaa\nMIDDLE\nzzz\n", "aaa\nCHANGED\nzzz\n");
    expect(edit.start).toBe(4);
    expect(edit.insert).toBe("CHANGED");
    expect(edit.deleteLength).toBe("MIDDLE".length);
  });
});
