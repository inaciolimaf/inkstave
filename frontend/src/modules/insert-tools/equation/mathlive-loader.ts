/**
 * Loads MathLive and its fonts on first use, so the equation editor stays out of the initial bundle (spec 114
 * §5.4). The fonts come from the stylesheet Vite bundles, not from a folder the server would have to serve.
 */
export async function loadMathLive(): Promise<void> {
  const [mathlive] = await Promise.all([import("mathlive"), import("mathlive/fonts.css")]);
  mathlive.MathfieldElement.fontsDirectory = null;
  mathlive.MathfieldElement.soundsDirectory = null;
}
