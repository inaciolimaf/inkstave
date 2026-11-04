import { describe, expect, it } from "vitest";

import { findMath, mathAt, wrapMath } from "./find-math";

/** The body the region finds, for a cursor placed at the middle of `marker`. */
function bodyAt(text: string, marker: string) {
  const offset = text.indexOf(marker) + Math.floor(marker.length / 2);
  return mathAt(text, offset)?.latex ?? null;
}

describe("findMath", () => {
  it.each([
    ["inline dollars", "x $a+b$ y", "a+b", "$", "$"],
    ["display dollars", "x $$a+b$$ y", "a+b", "$$", "$$"],
    ["inline parentheses", "x \\(a+b\\) y", "a+b", "\\(", "\\)"],
    ["display brackets", "x \\[a+b\\] y", "a+b", "\\[", "\\]"],
    ["equation", "\\begin{equation}a+b\\end{equation}", "a+b", "\\begin{equation}", "\\end{equation}"],
    ["starred align", "\\begin{align*}a&=b\\end{align*}", "a&=b", "\\begin{align*}", "\\end{align*}"],
    ["gather", "\\begin{gather}a\\end{gather}", "a", "\\begin{gather}", "\\end{gather}"],
    ["multline", "\\begin{multline*}a\\end{multline*}", "a", "\\begin{multline*}", "\\end{multline*}"],
  ])("finds %s with its delimiters", (_, text, latex, open, close) => {
    const [region] = findMath(text);
    expect(region?.latex).toBe(latex);
    expect(region?.delimiters).toEqual({ open, close });
    expect(text.slice(region!.from, region!.to)).toBe(latex);
  });

  it("does not treat an escaped dollar as a delimiter", () => {
    expect(findMath("costs \\$5 and \\$7")).toEqual([]);
    expect(findMath("$5 \\$ 6$")[0]?.latex).toBe("5 \\$ 6");
  });

  it("does not end math at an escaped backslash followed by a delimiter's worth of text", () => {
    expect(findMath("$a \\\\$ b")[0]?.latex).toBe("a \\\\");
  });

  it("ignores dollars inside a comment", () => {
    expect(findMath("% $ not math\nplain")).toEqual([]);
  });

  it("finds several regions in order, none overlapping", () => {
    const regions = findMath("$a$ text $b$");
    expect(regions.map((region) => region.latex)).toEqual(["a", "b"]);
  });

  it("skips an opener that never closes", () => {
    expect(findMath("$a and nothing more")).toEqual([]);
  });

  it("keeps nested braces inside the body", () => {
    expect(findMath("$\\frac{\\sqrt{a}}{b}$")[0]?.latex).toBe("\\frac{\\sqrt{a}}{b}");
  });
});

describe("mathAt", () => {
  it("finds the fraction the cursor is in, as the acceptance criteria describe", () => {
    const text = "Let $\\frac{a}{b}$ hold.";
    const cursor = text.indexOf("a}");
    expect(mathAt(text, cursor)).toMatchObject({
      latex: "\\frac{a}{b}",
      delimiters: { open: "$", close: "$" },
    });
  });

  it("counts the edges of the body as inside, and the delimiters as outside", () => {
    // x0 space1 $2 a3 b4 $5 space6
    const text = "x $ab$ y";
    expect(mathAt(text, 3)?.latex).toBe("ab");
    expect(mathAt(text, 5)?.latex).toBe("ab");
    expect(mathAt(text, 2)).toBeNull();
    expect(mathAt(text, 6)).toBeNull();
  });

  it("returns null in plain text", () => {
    expect(mathAt("plain text", 3)).toBeNull();
  });

  it("finds the body of an equation environment from inside it", () => {
    const text = "\\begin{equation}\n  E = mc^2\n\\end{equation}";
    expect(bodyAt(text, "mc^2")).toBe("\n  E = mc^2\n");
  });
});

describe("wrapMath", () => {
  it("writes inline math with \\( and \\)", () => {
    expect(wrapMath("x^2", false)).toBe("\\(x^2\\)");
  });

  it("writes displayed math as an equation environment", () => {
    expect(wrapMath("x^2", true)).toBe("\\begin{equation}\nx^2\n\\end{equation}");
  });
});
