import { describe, expect, it } from "vitest";

import { symbolInsert } from "./insert-symbol";
import { recentEntries, readRecent, RECENT_LIMIT, rememberRecent } from "./recent-symbols";
import { SYMBOL_CATEGORIES, SYMBOLS, findSymbol, searchSymbols } from "./symbol-data";

describe("symbols.json", () => {
  it("has unique commands, each starting with a backslash", () => {
    const commands = SYMBOLS.map((entry) => entry.command);
    expect(new Set(commands).size).toBe(commands.length);
    for (const command of commands) expect(command).toMatch(/^\\[^\\\s]+$/);
  });

  it("has only known categories, and every category is used", () => {
    const known = new Set<string>(SYMBOL_CATEGORIES);
    for (const entry of SYMBOLS) expect(known.has(entry.category)).toBe(true);
    for (const category of SYMBOL_CATEGORIES) {
      expect(SYMBOLS.some((entry) => entry.category === category)).toBe(true);
    }
  });

  it("gives every symbol a glyph, keywords and a sane argument count", () => {
    for (const entry of SYMBOLS) {
      expect(entry.unicode.length).toBeGreaterThan(0);
      expect(entry.keywords.length).toBeGreaterThan(0);
      expect(entry.args ?? 0).toBeGreaterThanOrEqual(0);
      expect(entry.args ?? 0).toBeLessThanOrEqual(2);
    }
  });

  it("names a package for each command that needs one", () => {
    expect(findSymbol("\\mathbb")).toMatchObject({ package: "amssymb", args: 1 });
    expect(findSymbol("\\alpha")?.package).toBeUndefined();
  });
});

describe("searchSymbols", () => {
  it("finds alpha by command, with the command match first", () => {
    const results = searchSymbols("alpha", "all");
    expect(results[0]?.command).toBe("\\alpha");
  });

  it("finds a symbol by a keyword, ignoring case and a leading backslash", () => {
    expect(searchSymbols("\\Infinity", "all").map((entry) => entry.command)).toContain("\\infty");
    expect(searchSymbols("INFINITY", "all").length).toBeGreaterThan(0);
  });

  it("narrows to one category", () => {
    const greek = searchSymbols("", "greek");
    expect(greek.length).toBeGreaterThan(30);
    expect(greek.every((entry) => entry.category === "greek")).toBe(true);
  });

  it("returns nothing for a query that matches no symbol", () => {
    expect(searchSymbols("zzqqxx", "all")).toEqual([]);
  });
});

describe("symbolInsert", () => {
  it("puts the cursor inside the braces of a command with an argument", () => {
    const frac = findSymbol("\\frac")!;
    expect(symbolInsert(frac, "")).toEqual({ insert: "\\frac{}{}", cursor: 6 });
  });

  it("adds a space when a letter would otherwise follow the command", () => {
    const alpha = findSymbol("\\alpha")!;
    expect(symbolInsert(alpha, "x")).toEqual({ insert: "\\alpha ", cursor: 7 });
    expect(symbolInsert(alpha, " ")).toEqual({ insert: "\\alpha", cursor: 6 });
  });
});

describe("recent symbols", () => {
  it("keeps the latest first, without repeats, up to the limit", () => {
    localStorage.clear();
    for (let i = 0; i < RECENT_LIMIT + 4; i++) rememberRecent(`\\cmd${i}`);
    rememberRecent("\\cmd5");
    const recent = readRecent();
    expect(recent).toHaveLength(RECENT_LIMIT);
    expect(recent[0]).toBe("\\cmd5");
    expect(recent.filter((item) => item === "\\cmd5")).toHaveLength(1);
  });

  it("drops commands that are no longer in the palette", () => {
    expect(recentEntries(["\\alpha", "\\not-a-symbol"]).map((entry) => entry.command)).toEqual(["\\alpha"]);
  });

  it("reads nothing when storage is blocked or holds junk", () => {
    localStorage.setItem("inkstave.insert.recent-symbols", "{not json");
    expect(readRecent()).toEqual([]);
    localStorage.clear();
  });
});
