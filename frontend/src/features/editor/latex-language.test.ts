import { LanguageSupport } from "@codemirror/language";
import { describe, expect, it } from "vitest";

import { latex, latexStreamLanguage } from "./latex-language";

describe("LaTeX language", () => {
  it("is a CodeMirror LanguageSupport (independent, permissive package)", () => {
    expect(latex()).toBeInstanceOf(LanguageSupport);
    expect(latexStreamLanguage.name).toBe("latex");
  });

  it("exposes a parser (highlighting wired)", () => {
    expect(latexStreamLanguage.parser).toBeTruthy();
  });
});
