import { describe, expect, it } from "vitest";

import { DEFAULT_OPTIONS, buildMatcher, escapeRegExp } from "./matcher";
import type { SearchOptions } from "./matcher";

function matchesOf(text: string, query: string, options: Partial<SearchOptions> = {}): string[] {
  const matcher = buildMatcher(query, { ...DEFAULT_OPTIONS, ...options });
  if (!matcher?.ok) throw new Error("expected a pattern");
  return [...text.matchAll(matcher.pattern)].map((m) => m[0]);
}

describe("buildMatcher", () => {
  it("is null for an empty query", () => {
    expect(buildMatcher("", DEFAULT_OPTIONS)).toBeNull();
  });

  it("treats a plain query literally, LaTeX and regex characters included", () => {
    expect(matchesOf("\\ref{fig:a} and \\ref{fig:a}.", "\\ref{fig:a}")).toHaveLength(2);
    expect(matchesOf("a.b axb", "a.b")).toEqual(["a.b"]);
    expect(escapeRegExp("$1 (x)")).toBe("\\$1 \\(x\\)");
  });

  it("ignores case unless asked", () => {
    expect(matchesOf("Rede rede REDE", "rede")).toHaveLength(3);
    expect(matchesOf("Rede rede REDE", "rede", { caseSensitive: true })).toEqual(["rede"]);
  });

  it("matches whole words of any script", () => {
    expect(matchesOf("rede redes subrede rede_x rede.", "rede", { wholeWord: true })).toHaveLength(2);
    expect(matchesOf("ação ações", "ação", { wholeWord: true })).toEqual(["ação"]);
  });

  it("runs a regular expression, with ^ and $ per line", () => {
    expect(matchesOf("fig:a fig:bb", "fig:\\w+", { regex: true })).toEqual(["fig:a", "fig:bb"]);
    expect(matchesOf("a\nab\nb", "^a", { regex: true })).toHaveLength(2);
  });

  it("accepts a pattern only the older syntax allows", () => {
    expect(matchesOf("a-b", "a\\-b", { regex: true })).toEqual(["a-b"]);
  });

  it("reports an invalid regular expression instead of throwing", () => {
    const matcher = buildMatcher("(unclosed", { ...DEFAULT_OPTIONS, regex: true });
    expect(matcher?.ok).toBe(false);
  });
});
