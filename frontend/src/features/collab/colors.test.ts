import { describe, expect, it } from "vitest";

import { colorForUser, colorLight, initials, PRESENCE_PALETTE } from "./colors";

describe("colorForUser", () => {
  it("is deterministic: same id -> same color (AC3)", () => {
    expect(colorForUser("user-123")).toBe(colorForUser("user-123"));
  });

  it("returns a palette color", () => {
    expect(PRESENCE_PALETTE).toContain(colorForUser("anything"));
  });

  it("spreads ids across the palette", () => {
    const seen = new Set(Array.from({ length: 50 }, (_, i) => colorForUser(`u${i}`)));
    expect(seen.size).toBeGreaterThan(3);
  });
});

describe("colorLight", () => {
  it("produces a translucent rgba of the hex", () => {
    expect(colorLight("#2563eb", 0.25)).toBe("rgba(37, 99, 235, 0.25)");
  });
});

describe("initials", () => {
  it.each([
    ["Ada Lovelace", "AL"],
    ["Grace", "GR"],
    ["  ", "?"],
  ])("%s -> %s", (name, expected) => {
    expect(initials(name)).toBe(expected);
  });
});
