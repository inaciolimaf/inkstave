import { describe, expect, it } from "vitest";

import { sanitizeDownloadName } from "./download";

describe("sanitizeDownloadName", () => {
  it("strips path separators and quotes, collapses whitespace", () => {
    expect(sanitizeDownloadName('My "Thesis"/v2')).toBe("My Thesis v2");
  });

  it("strips control characters", () => {
    expect(sanitizeDownloadName("a\nb\tc")).toBe("a b c");
  });

  it("falls back to 'project' when empty", () => {
    expect(sanitizeDownloadName("   ")).toBe("project");
    expect(sanitizeDownloadName("///")).toBe("project");
  });
});
