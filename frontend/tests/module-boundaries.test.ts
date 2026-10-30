import { readdirSync, readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const MODULES = readdirSync("src/modules");

function dependenciesOf(name: string): Set<string> {
  const root = `src/modules/${name}`;
  const sources = readdirSync(root, { recursive: true, encoding: "utf-8" })
    .filter((path) => /\.tsx?$/.test(path) && !path.includes(".test."))
    .map((path) => `${root}/${path}`);
  const imported = sources.flatMap((path) =>
    [...readFileSync(path, "utf-8").matchAll(/from "@\/modules\/([a-z-]+)/g)].map((match) => match[1]),
  );
  return new Set(imported.filter((target) => target !== name));
}

function findCycle(graph: Map<string, Set<string>>): string[] | null {
  const walk = (node: string, path: string[]): string[] | null => {
    if (path.includes(node)) return [...path.slice(path.indexOf(node)), node];
    for (const next of graph.get(node) ?? []) {
      const cycle = walk(next, [...path, node]);
      if (cycle) return cycle;
    }
    return null;
  };
  for (const node of graph.keys()) {
    const cycle = walk(node, []);
    if (cycle) return cycle;
  }
  return null;
}

describe("module boundaries", () => {
  it("has no import cycle between modules", () => {
    const graph = new Map(MODULES.map((name) => [name, dependenciesOf(name)]));
    expect(findCycle(graph)).toBeNull();
  });
});
