import { describe, expect, it } from "vitest";

import type { TreeNode } from "@/modules/file-tree";

import { selectionAfterTreeChange } from "./selection-follows-tree";

const doc: TreeNode = {
  id: "d1",
  name: "a.tex",
  type: "doc",
  parentId: "root",
  isRoot: false,
  path: "a.tex",
  children: [],
};

describe("selectionAfterTreeChange", () => {
  it("leaves a selection the tree still has at the same path", () => {
    expect(selectionAfterTreeChange(new Set(["d1"]), new Map([["d1", doc]]), doc)).toBeUndefined();
  });

  it("clears a selection that was removed", () => {
    expect(selectionAfterTreeChange(new Set(["d1"]), new Map(), doc)).toBeNull();
  });

  it("does not clear a file created before the tree refetched", () => {
    expect(selectionAfterTreeChange(new Set(), new Map(), doc)).toBeUndefined();
  });

  it("follows a rename or a move", () => {
    const moved = { ...doc, name: "b.tex", path: "src/b.tex" };
    expect(selectionAfterTreeChange(new Set(["d1"]), new Map([["d1", moved]]), doc)).toBe(moved);
  });
});
