import { describe, expect, it } from "vitest";

import { withQuote } from "./quote";

describe("withQuote", () => {
  it("leaves a plain message alone", () => {
    expect(withQuote("Shorten this", null)).toBe("Shorten this");
  });
  it("carries the selected text and where it came from", () => {
    const quote = { path: "sec/intro.tex", fromLine: 3, toLine: 4, text: "Hello" };
    const message = withQuote("Shorten this", quote);
    expect(message.startsWith("Shorten this")).toBe(true);
    expect(message).toContain("sec/intro.tex, lines 3-4");
    expect(message).toContain("```\nHello\n```");
  });
});
