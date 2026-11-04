import { describe, expect, it } from "vitest";

import type { TreeNode } from "@/modules/file-tree";

import {
  MAX_INDEXED_CHARS,
  MAX_INDEXED_DOCUMENTS,
  buildIndex,
  listDocuments,
  withLiveText,
} from "./build-index";

const docs = (count: number) => Array.from({ length: count }, (_, i) => ({ id: `d${i}`, path: `f${i}.tex` }));

function node(partial: Partial<TreeNode> & Pick<TreeNode, "id" | "type" | "path">): TreeNode {
  return { name: partial.path, parentId: null, isRoot: false, children: [], ...partial };
}

describe("listDocuments", () => {
  it("lists the documents of the tree, not its folders or files", () => {
    const root = node({
      id: "root",
      type: "folder",
      path: "",
      isRoot: true,
      children: [
        node({ id: "a", type: "doc", path: "main.tex" }),
        node({
          id: "f",
          type: "folder",
          path: "chapters",
          children: [node({ id: "b", type: "doc", path: "chapters/intro.tex" })],
        }),
        node({ id: "img", type: "file", path: "fig.png" }),
      ],
    });
    expect(listDocuments(root)).toEqual([
      { id: "a", path: "main.tex" },
      { id: "b", path: "chapters/intro.tex" },
    ]);
  });

  it("is empty before the tree arrives", () => {
    expect(listDocuments(undefined)).toEqual([]);
  });
});

describe("buildIndex", () => {
  it("parses every fetched text", () => {
    const { index, limited } = buildIndex(docs(2), ["\\section{A}", "\\section{B}"], null);
    expect(limited).toBe(false);
    expect(index.get("d1")?.items).toEqual([{ kind: "section", level: 2, title: "B", line: 1 }]);
  });

  it("skips documents that were not fetched", () => {
    const { index } = buildIndex(docs(2), ["\\section{A}", undefined], null);
    expect([...index.keys()]).toEqual(["d0"]);
  });

  it("keeps only the open file past the document cap", () => {
    const many = docs(MAX_INDEXED_DOCUMENTS + 1);
    const texts = many.map(() => "\\section{X}");
    const { index, limited } = buildIndex(many, texts, "d3");
    expect(limited).toBe(true);
    expect([...index.keys()]).toEqual(["d3"]);
  });

  it("keeps only the open file past the text cap", () => {
    const big = "x".repeat(MAX_INDEXED_CHARS);
    const { index, limited } = buildIndex(docs(2), [big, "\\section{B}"], "d1");
    expect(limited).toBe(true);
    expect([...index.keys()]).toEqual(["d1"]);
  });
});

describe("withLiveText", () => {
  it("replaces the open file's fetched copy with its live text", () => {
    const { index } = buildIndex(docs(1), ["\\section{Saved}"], "d0");
    const live = withLiveText(index, docs(1), "d0", "\\section{Typed}");
    expect(live.get("d0")?.items[0].title).toBe("Typed");
    expect(index.get("d0")?.items[0].title).toBe("Saved");
  });

  it("leaves the index alone while there is no live text", () => {
    const { index } = buildIndex(docs(1), ["\\section{Saved}"], "d0");
    expect(withLiveText(index, docs(1), "d0", null).get("d0")?.items[0].title).toBe("Saved");
  });
});
