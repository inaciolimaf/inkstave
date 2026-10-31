import { describe, expect, it } from "vitest";

import type { TreeNode } from "@/modules/file-tree";

import { pickStartDocument } from "./start-document";

const node = (id: string, name: string, type: TreeNode["type"], children: TreeNode[] = []) =>
  ({ id, name, type, path: name, children }) as unknown as TreeNode;

const tree = node("root", "", "folder", [
  node("a", "notes.md", "doc"),
  node("f", "Paper", "folder", [node("b", "main.tex", "doc"), node("c", "intro.tex", "doc")]),
]);

describe("pickStartDocument", () => {
  it("prefers the project's root document", () => {
    expect(pickStartDocument(tree, "c")?.id).toBe("c");
  });
  it("falls back to main.tex, even inside a folder", () => {
    expect(pickStartDocument(tree, null)?.id).toBe("b");
  });
  it("then to any .tex, then to any document", () => {
    const noMain = node("root", "", "folder", [node("a", "notes.md", "doc"), node("c", "intro.tex", "doc")]);
    expect(pickStartDocument(noMain, null)?.id).toBe("c");
    expect(pickStartDocument(node("root", "", "folder", [node("a", "notes.md", "doc")]), null)?.id).toBe("a");
  });
  it("finds nothing in a project with no documents", () => {
    expect(pickStartDocument(node("root", "", "folder"), null)).toBeNull();
  });
});
