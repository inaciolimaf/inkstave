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
