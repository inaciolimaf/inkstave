/**
 * The only place with fixed content colours: values that identify content, not the theme, so a
 * design token does not apply. Everything else uses the tokens in `index.css`.
 */

/** Caret/ring colours for collaborators (≈ AA contrast on light and dark editor backgrounds). */
export const PRESENCE_PALETTE: readonly string[] = [
  "#2563eb", // blue
  "#dc2626", // red
  "#16a34a", // green
  "#d97706", // amber
  "#7c3aed", // violet
  "#0891b2", // cyan
  "#db2777", // pink
  "#65a30d", // lime
  "#ea580c", // orange
  "#0d9488", // teal
];

/** Shown for a peer whose awareness state carries no colour. */
export const PRESENCE_FALLBACK_COLOR = "#888888";

const INK_ON_LIGHT = "#111827";
const INK_ON_DARK = "#ffffff";

function linearChannel(hexPair: string): number {
  const value = parseInt(hexPair, 16) / 255;
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

/** The ink for text over a presence colour: the theme's foreground changes, the colour does not. */
export function inkOn(color: string): string {
  const [red, green, blue] = [1, 3, 5].map((start) => linearChannel(color.slice(start, start + 2)));
  const luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  // Where #ffffff and #111827 give the same WCAG ratio over the colour.
  return luminance > 0.18 ? INK_ON_LIGHT : INK_ON_DARK;
}
