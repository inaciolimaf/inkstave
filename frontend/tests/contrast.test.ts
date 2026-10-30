import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const TEXT = 4.5; // WCAG 2.2 SC 1.4.3, body text.
const CONTROL = 3; // WCAG 2.2 SC 1.4.11, focus outlines and control borders.

// [foreground, background], without the leading `--`.
const TEXT_PAIRS = [
  ["foreground", "background"],
  ["card-foreground", "card"],
  ["popover-foreground", "popover"],
  ["muted-foreground", "background"],
  ["muted-foreground", "muted"],
  ["primary-foreground", "primary"],
  ["secondary-foreground", "secondary"],
  ["accent-foreground", "accent"],
  ["destructive-foreground", "destructive"],
  ["on-success", "success"],
  ["on-warning", "warning"],
  ["success-text", "success-soft"],
  ["warning-text", "warning-soft"],
  ["error-text", "error-soft"],
  ["error-text", "background"],
] as const;

const CONTROL_PAIRS = [
  ["focus", "background"],
  ["focus", "card"],
  ["focus", "muted"],
  ["border-strong", "background"],
] as const;

type Theme = Map<string, string>;

function parseTheme(css: string, selector: RegExp): Theme {
  const blocks = [...css.matchAll(selector)].map((match) => match[1]).join("\n");
  const channels = /--([a-z-]+):\s*([\d.]+ [\d.]+% [\d.]+%)\s*;/g;
  return new Map([...blocks.matchAll(channels)].map((match) => [match[1], match[2]]));
}

function relativeLuminance(channels: string): number {
  const [hue, saturation, lightness] = channels.split(" ").map(parseFloat);
  const chroma = (saturation / 100) * Math.min(lightness / 100, 1 - lightness / 100);
  const channel = (offset: number) => {
    const position = (offset + hue / 30) % 12;
    const value = lightness / 100 - chroma * Math.max(-1, Math.min(position - 3, 9 - position, 1));
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(8) + 0.0722 * channel(4);
}

function contrast(first: string, second: string): number {
  const [low, high] = [relativeLuminance(first), relativeLuminance(second)].sort((a, b) => a - b);
  return (high + 0.05) / (low + 0.05);
}

function failures(theme: Theme, pairs: readonly (readonly [string, string])[], minimum: number): string[] {
  return pairs.flatMap(([foreground, background]) => {
    const ratio = contrast(theme.get(foreground) ?? "", theme.get(background) ?? "");
    return ratio >= minimum ? [] : [`${foreground} on ${background}: ${ratio.toFixed(2)}`];
  });
}

const css = readFileSync("src/index.css", "utf-8");
const themes = {
  light: parseTheme(css, /:root\s*\{([^}]*)\}/g),
  dark: parseTheme(css, /\.dark\s*\{([^}]*)\}/g),
};

describe("contrast", () => {
  it("measures the WCAG ratio", () => {
    expect(contrast("0 0% 0%", "0 0% 100%")).toBeCloseTo(21);
    expect(contrast("0 100% 50%", "0 0% 100%")).toBeCloseTo(4, 0);
  });

  describe.each(Object.entries(themes))("%s theme", (_, theme) => {
    it("declares every colour of the pairs", () => {
      const names = [...TEXT_PAIRS, ...CONTROL_PAIRS].flat();
      expect(names.filter((name) => !theme.has(name))).toEqual([]);
    });

    it(`keeps text at ${TEXT}:1`, () => {
      expect(failures(theme, TEXT_PAIRS, TEXT)).toEqual([]);
    });

    it(`keeps focus and control borders at ${CONTROL}:1`, () => {
      expect(failures(theme, CONTROL_PAIRS, CONTROL)).toEqual([]);
    });
  });
});
