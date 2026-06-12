import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterEach, describe, expect, it } from "vitest";

import type { TreeNode } from "@/features/file-tree/types";

import { cursorLine, findNodeByPath, revealLine, syncHighlightExtension } from "./sync-decoration";

function makeView(doc: string): EditorView {
  const parent = document.createElement("div");
  document.body.appendChild(parent);
  return new EditorView({
    state: EditorState.create({ doc, extensions: [syncHighlightExtension] }),
    parent,
  });
}

let view: EditorView | null = null;
afterEach(() => {
  view?.destroy();
  view = null;
});

describe("revealLine", () => {
  it("moves the cursor to the target line and flashes it", () => {
    view = makeView("one\ntwo\nthree\nfour");
    revealLine(view, 3);
    expect(cursorLine(view)).toBe(3);
    expect(view.dom.querySelector(".cm-sync-flash")).not.toBeNull();
  });

  it("clamps an out-of-range line to the document bounds", () => {
    view = makeView("a\nb");
    revealLine(view, 99);
    expect(cursorLine(view)).toBe(2);
  });
});

describe("findNodeByPath", () => {
  const tree: TreeNode = {
    id: "root",
    name: "",
    type: "folder",
    parentId: null,
    isRoot: true,
    path: "",
    children: [
      {
        id: "m",
        name: "main.tex",
        type: "doc",
        parentId: "root",
        isRoot: false,
        path: "main.tex",
        children: [],
      },
      {
        id: "s",
        name: "sections",
        type: "folder",
        parentId: "root",
        isRoot: false,
        path: "sections",
        children: [
          {
            id: "i",
            name: "intro.tex",
            type: "doc",
            parentId: "s",
            isRoot: false,
            path: "sections/intro.tex",
            children: [],
          },
        ],
      },
    ],
  };

  it("finds a nested node by its project-relative path", () => {
    expect(findNodeByPath(tree, "sections/intro.tex")?.id).toBe("i");
    expect(findNodeByPath(tree, "main.tex")?.id).toBe("m");
  });

  it("returns null for an unknown path", () => {
    expect(findNodeByPath(tree, "nope.tex")).toBeNull();
  });
});
