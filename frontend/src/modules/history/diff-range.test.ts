import { describe, expect, it } from "vitest";

import { diffRange } from "./diff-range";

describe("diffRange", () => {
  it("shows nothing until a version is selected", () => {
    expect(diffRange(null, null)).toEqual({ from: null, to: null });
  });

  it("shows what a version changed, against the one before it", () => {
    expect(diffRange(30, null)).toEqual({ from: 29, to: 30 });
  });

  it("compares the first version with the current text", () => {
    expect(diffRange(1, null)).toEqual({ from: 1, to: "current" });
  });

  it("compares two selected versions, oldest first", () => {
    expect(diffRange(30, 12)).toEqual({ from: 12, to: 30 });
  });
});
