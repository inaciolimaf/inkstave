/**
 * Deterministic per-user color assignment for presence (spec 32).
 *
 * A fixed palette of high-contrast, accessible hues; a user id hashes into it so
 * the same user maps to the same color on every client without coordination. The
 * color is also published in awareness so peers agree even if they disagreed.
 * Trade-off: within a small present set a hash collision is possible (two users
 * same color) — deterministic-and-stable is preferred over guaranteed-unique.
 */

/** Caret/ring colors (≈ AA contrast on both light and dark editor backgrounds). */
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

function hash(value: string): number {
  // FNV-1a (32-bit) — stable across clients/runtimes.
  let h = 0x811c9dc5;
  for (let i = 0; i < value.length; i++) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** The stable caret/ring color for a user id. */
export function colorForUser(userId: string): string {
  return PRESENCE_PALETTE[hash(userId) % PRESENCE_PALETTE.length];
}

/** A translucent variant of a hex color for tinting remote selections. */
export function colorLight(hex: string, alpha = 0.25): string {
  const value = hex.replace("#", "");
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Up-to-two-letter initials for an avatar fallback. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
