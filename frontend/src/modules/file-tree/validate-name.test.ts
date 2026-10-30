import { describe, expect, it } from "vitest";

import { validateEntityName } from "./validate-name";

describe("validateEntityName", () => {
  it("accepts a normal name", () => {
    expect(validateEntityName("chapter1.tex")).toBeNull();
  });

  it("rejects empty and whitespace-only names", () => {
    expect(validateEntityName("")).toMatch(/required/);
    expect(validateEntityName("   ")).toMatch(/required/);
  });

  it("rejects path separators", () => {
    expect(validateEntityName("a/b")).toMatch(/slash/);
    expect(validateEntityName("a\\b")).toMatch(/slash/);
  });

  it("rejects dot names", () => {
    expect(validateEntityName(".")).toMatch(/cannot be/);
    expect(validateEntityName("..")).toMatch(/cannot be/);
  });

  it("rejects names longer than 255 chars", () => {
    expect(validateEntityName("x".repeat(256))).toMatch(/at most 255/);
  });

  it("rejects control characters", () => {
    expect(validateEntityName(`a${String.fromCharCode(1)}b`)).toMatch(/control/);
  });
});
