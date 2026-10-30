import jetbrainsLatinExt from "@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-ext-wght-normal.woff2";
import jetbrainsLatin from "@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2";
import newsreaderLatinExt from "@fontsource-variable/newsreader/files/newsreader-latin-ext-opsz-normal.woff2";
import newsreaderLatin from "@fontsource-variable/newsreader/files/newsreader-latin-opsz-normal.woff2";

/*
 * The faces every screen may need: `font-mono` (JetBrains Mono) and the logo's
 * `font-serif` (upright Newsreader). Inter and Newsreader italics are landing-only
 * and live in modules/landing/landing.css.
 *
 * Registered here rather than through Fontsource's stylesheets so that only latin
 * and latin-ext reach the build. A registered face downloads only when a screen
 * first renders a glyph from it; latin-ext stays unloaded for Portuguese text.
 */
const LATIN =
  "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD";
const LATIN_EXT =
  "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF";

function register(family: string, weight: string, url: string, unicodeRange: string) {
  const face = new FontFace(family, `url(${url}) format("woff2")`, { weight, unicodeRange, display: "swap" });
  document.fonts.add(face);
}

register("JetBrains Mono Variable", "100 800", jetbrainsLatin, LATIN);
register("JetBrains Mono Variable", "100 800", jetbrainsLatinExt, LATIN_EXT);
register("Newsreader Variable", "200 800", newsreaderLatin, LATIN);
register("Newsreader Variable", "200 800", newsreaderLatinExt, LATIN_EXT);
