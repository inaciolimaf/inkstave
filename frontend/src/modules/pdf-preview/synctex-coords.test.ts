import { describe, expect, it } from "vitest";

import { boxToCssRect, cssToPdfPoint } from "./synctex-coords";

describe("cssToPdfPoint", () => {
  it("divides CSS pixels by the viewport scale", () => {
    expect(cssToPdfPoint(120, 80, 2)).toEqual({ h: 60, v: 40 });
  });

  it("treats a zero scale as 1 (no divide-by-zero)", () => {
    expect(cssToPdfPoint(10, 20, 0)).toEqual({ h: 10, v: 20 });
  });
});

describe("boxToCssRect", () => {
  it("positions the box top at the baseline minus its height", () => {
    const box = { page: 1, h: 10, v: 20, width: 30, height: 5, depth: 2 };
    expect(boxToCssRect(box, 2)).toEqual({ left: 20, top: 30, width: 60, height: 14 });
  });

  it("floors width/height at 2px for zero-size leaf boxes", () => {
    const box = { page: 1, h: 10, v: 20, width: 0, height: 0, depth: 0 };
    const rect = boxToCssRect(box, 1);
    expect(rect.width).toBe(2);
    expect(rect.height).toBe(2);
  });
});
