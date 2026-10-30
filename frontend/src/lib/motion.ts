/** Timings for code that needs them in JavaScript; the CSS source is `--motion-*` in src/index.css. */
export const DURATION = { fast: 150, base: 250, slow: 400 } as const;

/** Guards a missing `matchMedia`, which jsdom does not provide. */
export function reducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}
