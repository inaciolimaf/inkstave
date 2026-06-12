import { describe, expect, it } from "vitest";

import {
  addChild,
  findNode,
  flattenVisible,
  isSelfOrDescendant,
  removeNode,
  reparent,
  sortNodes,
  updateNode,
} from "./tree-utils";
import type { TreeNode } from "./types";

function node(
  id: string,
  type: TreeNode["type"],
  name: string,
  children: TreeNode[] = [],
): TreeNode {
  return { id, name, type, parentId: null, isRoot: id === "root", path: name, children };
}

const tree = node("root", "folder", "root", [
  node("z-doc", "doc", "z.tex"),
  node("a-folder", "folder", "Assets", [node("img", "file", "logo.png")]),
  node("a-doc", "doc", "a.tex"),
]);

describe("sortNodes", () => {
  it("orders folders first, then alphabetical (case-insensitive)", () => {
    expect(sortNodes(tree.children).map((n) => n.name)).toEqual(["Assets", "a.tex", "z.tex"]);
  });
});

describe("flattenVisible", () => {
  it("excludes children of collapsed folders", () => {
    const flat = flattenVisible(tree, new Set());
    expect(flat.map((f) => f.node.name)).toEqual(["Assets", "a.tex", "z.tex"]);
  });

  it("includes children of expanded folders with correct depth", () => {
    const flat = flattenVisible(tree, new Set(["a-folder"]));
    expect(flat.map((f) => f.node.name)).toEqual(["Assets", "logo.png", "a.tex", "z.tex"]);
    expect(flat.find((f) => f.node.name === "logo.png")?.depth).toBe(1);
  });
});

describe("isSelfOrDescendant", () => {
  it("detects a folder dropped into its own descendant", () => {
    expect(isSelfOrDescendant(tree, "a-folder", "img")).toBe(true);
    expect(isSelfOrDescendant(tree, "a-folder", "a-folder")).toBe(true);
    expect(isSelfOrDescendant(tree, "a-folder", "z-doc")).toBe(false);
  });
});

describe("immutable mutations", () => {
  it("addChild inserts under the right parent", () => {
    const next = addChild(tree, "a-folder", node("new", "doc", "n.tex"));
    expect(findNode(next, "a-folder")?.children.map((c) => c.id)).toContain("new");
    expect(tree).not.toBe(next); // immutable
  });

  it("updateNode patches a node", () => {
    expect(findNode(updateNode(tree, "z-doc", { name: "renamed.tex" }), "z-doc")?.name).toBe(
      "renamed.tex",
    );
  });

  it("removeNode deletes a subtree", () => {
    expect(findNode(removeNode(tree, "a-folder"), "img")).toBeNull();
  });

  it("reparent moves a node and updates its parentId", () => {
    const next = reparent(tree, "z-doc", "a-folder");
    expect(findNode(next, "a-folder")?.children.map((c) => c.id)).toContain("z-doc");
    expect(findNode(next, "z-doc")?.parentId).toBe("a-folder");
  });
});
