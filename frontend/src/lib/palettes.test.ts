import { describe, expect, it } from "vitest";

import { PRESENCE_FALLBACK_COLOR, PRESENCE_PALETTE, inkOn } from "./palettes";

function luminance(color: string): number {
  const channels = [1, 3, 5].map((start) => {
    const value = parseInt(color.slice(start, start + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(first: string, second: string): number {
  const [low, high] = [luminance(first), luminance(second)].sort((a, b) => a - b);
  return (high + 0.05) / (low + 0.05);
}

describe("inkOn", () => {
  it.each([...PRESENCE_PALETTE, PRESENCE_FALLBACK_COLOR])("is readable over %s", (color) => {
    expect(contrast(inkOn(color), color)).toBeGreaterThanOrEqual(4.5);
  });
});
