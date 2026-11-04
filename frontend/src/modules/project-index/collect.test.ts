import { describe, expect, it } from "vitest";

import type { TreeNode } from "@/modules/file-tree";

import { type DocRef, collectBib, collectLabels, listFiles } from "./build-index";
import type { IndexedDoc } from "./resolve-includes";

const docs: DocRef[] = [
  { id: "main", path: "main.tex" },
  { id: "refs", path: "refs.bib" },
  { id: "more", path: "more.bib" },
];

describe("collectBib", () => {
  it("lists each key once, from the first file that defines it, and names the other files", () => {
    const texts = [
      undefined,
      "@article{silva2023, title={Deep}, author={Silva, A.}, year={2023}}\n@book{dup, title={First}}",
      "@book{dup, title={Second}}\n@misc{only, year={2001}}",
    ];
    const refs = collectBib(docs, texts, null, null);
    expect(refs.map((ref) => ref.key)).toEqual(["silva2023", "dup", "only"]);
    expect(refs.find((ref) => ref.key === "dup")).toMatchObject({
      title: "First",
      path: "refs.bib",
      alsoIn: ["more.bib"],
    });
    expect(refs.find((ref) => ref.key === "silva2023")?.alsoIn).toBeUndefined();
  });

  it("reads the live text of the open bibliography file, not its fetched copy", () => {
    const texts = [undefined, "@misc{old}", undefined];
    const refs = collectBib(docs, texts, "refs", "@misc{fresh}");
    expect(refs.map((ref) => ref.key)).toEqual(["fresh"]);
  });

  it("ignores documents that are not bibliographies and documents not fetched", () => {
    const refs = collectBib(docs, ["@misc{not_bib}", undefined, undefined], null, null);
    expect(refs).toEqual([]);
  });
});

function indexed(id: string, path: string, lines: string[]): IndexedDoc {
  return { id, path, items: lines.map((line, i) => parseLine(line, i + 1)) };
}

function parseLine(line: string, number: number): IndexedDoc["items"][number] {
  const [kind, ...rest] = line.split(":");
  const value = rest.join(":");
  if (kind === "section") return { kind: "section", level: 2, title: value, line: number };
  return { kind: "label", title: value, line: number };
}

describe("collectLabels", () => {
  it("lists labels of every indexed file with the section each falls under", () => {
    const docs = new Map([
      ["main", indexed("main", "main.tex", ["section:Intro", "label:sec:intro"])],
      ["figs", indexed("figs", "figures.tex", ["label:fig:plot", "section:Results", "label:fig:bars"])],
    ]);
    expect(collectLabels(docs)).toEqual([
      { name: "sec:intro", docId: "main", path: "main.tex", section: "Intro", line: 2 },
      { name: "fig:plot", docId: "figs", path: "figures.tex", section: undefined, line: 1 },
      { name: "fig:bars", docId: "figs", path: "figures.tex", section: "Results", line: 3 },
    ]);
  });
});

function node(type: TreeNode["type"], path: string, children: TreeNode[] = [], isRoot = false): TreeNode {
  return { id: path, name: path, type, parentId: null, isRoot, path, children };
}

describe("listFiles", () => {
  it("lists documents and files of the tree, without folders or the root", () => {
    const root = node(
      "folder",
      "",
      [node("doc", "main.tex"), node("folder", "images", [node("file", "images/plot.png")])],
      true,
    );
    expect(listFiles(root)).toEqual([
      { path: "main.tex", type: "doc" },
      { path: "images/plot.png", type: "file" },
    ]);
    expect(listFiles(undefined)).toEqual([]);
  });
});
