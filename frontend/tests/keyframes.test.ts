import { readdirSync, readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

// What the compositor can animate without layout or paint; the motion rule of the frontend standard.
const CHEAP_PROPERTIES = new Set([
  "transform",
  "translate",
  "rotate",
  "scale",
  "opacity",
  "stroke-dashoffset",
  "stroke-dasharray",
]);

type Keyframes = { name: string; properties: string[] };

function matchingBrace(css: string, open: number): number {
  let depth = 0;
  for (let index = open; index < css.length; index += 1) {
    if (css[index] === "{") depth += 1;
    if (css[index] === "}" && --depth === 0) return index;
  }
  throw new Error("Unbalanced braces in a stylesheet");
}

function parseKeyframes(source: string): Keyframes[] {
  const css = source.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...css.matchAll(/@(?:-[a-z]+-)?keyframes\s+([^\s{]+)\s*\{/g)].map((match) => {
    const open = match.index + match[0].length - 1;
    const body = css.slice(open + 1, matchingBrace(css, open));
    return { name: match[1], properties: [...body.matchAll(/([a-z-]+)\s*:/g)].map((found) => found[1]) };
  });
}

const stylesheets = readdirSync("src", { recursive: true, encoding: "utf-8" })
  .filter((path) => path.endsWith(".css"))
  .map((path) => ({ path: `src/${path}`, css: readFileSync(`src/${path}`, "utf-8") }));

const animated = stylesheets.filter(({ css }) => parseKeyframes(css).length > 0);

describe("@keyframes", () => {
  it("reads the properties of each step, comments aside", () => {
    const css =
      "/* @keyframes old { to { top: 0 } } */ @keyframes a { from { opacity: 0; width: 0 } to { top: 1px } }";
    expect(parseKeyframes(css)).toEqual([{ name: "a", properties: ["opacity", "width", "top"] }]);
  });

  it("finds the stylesheets it is meant to guard", () => {
    expect(animated.map(({ path }) => path)).toContain("src/modules/landing/landing.css");
  });

  it("animates only properties that skip layout and paint", () => {
    const expensive = animated.flatMap(({ path, css }) =>
      parseKeyframes(css).flatMap(({ name, properties }) =>
        properties.filter((property) => !CHEAP_PROPERTIES.has(property)).map((p) => `${path} ${name}: ${p}`),
      ),
    );
    expect(expensive).toEqual([]);
  });

  it("comes with a reduced-motion path in the same stylesheet", () => {
    const unguarded = animated.filter(({ css }) => !css.includes("prefers-reduced-motion"));
    expect(unguarded.map(({ path }) => path)).toEqual([]);
  });
});
