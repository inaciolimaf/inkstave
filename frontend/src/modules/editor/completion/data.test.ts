import { describe, expect, it } from "vitest";

import { loadStaticData } from "./load-data";

/** The data files are generated and hand-written, so a duplicate or an unsorted entry is caught here. */
describe("completion data", () => {
  it("has sorted, unique command names of about the planned size", async () => {
    const { commands } = await loadStaticData();
    const names = commands.map((entry) => entry.name);
    expect(names).toEqual([...names].sort());
    expect(new Set(names).size).toBe(names.length);
    expect(names.length).toBeGreaterThan(350);
  });

  it("has sorted, unique environment names with a body for each", async () => {
    const { environments } = await loadStaticData();
    const names = environments.map((entry) => entry.name);
    expect(names).toEqual([...names].sort());
    expect(new Set(names).size).toBe(names.length);
    for (const entry of environments) {
      expect(entry.snippet.startsWith("\\begin{@NAME@}")).toBe(true);
      expect(entry.snippet.endsWith("\\end{@NAME@}")).toBe(true);
    }
  });

  it("has sorted, unique package names", async () => {
    const { packages } = await loadStaticData();
    expect(packages).toEqual([...packages].sort());
    expect(new Set(packages).size).toBe(packages.length);
    expect(packages).toEqual(expect.arrayContaining(["amsmath", "graphicx", "hyperref", "booktabs"]));
  });

  it("gives every command a hint and every snippet a field or nothing", async () => {
    const { commands } = await loadStaticData();
    for (const entry of commands) {
      expect(entry.hint.length).toBeGreaterThan(0);
      if (entry.snippet) expect(entry.snippet.startsWith("\\")).toBe(true);
    }
  });
});
