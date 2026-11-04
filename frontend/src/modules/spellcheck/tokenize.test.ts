import { describe, expect, it } from "vitest";

import { checkableWords } from "./tokenize";

/** The checkable words of a whole text, as plain strings. */
function words(text: string): string[] {
  return checkableWords(text, 0, text.length).map((w) => w.word);
}

describe("checkableWords: what is checked", () => {
  it.each([
    ["plain prose", "This is teh text.", ["This", "is", "teh", "text"]],
    ["words inside emphasis", "\\emph{teh} and \\textbf{wrold}", ["teh", "and", "wrold"]],
    [
      "section, caption and footnote text",
      "\\section{Intro}\\caption{Figre}\\footnote{Notse}",
      ["Intro", "Figre", "Notse"],
    ],
    ["a line break argument is not a word", "one\\\\ two", ["one", "two"]],
    [
      "the first argument of href is skipped, the text is checked",
      "\\href{https://teh.example}{the site}",
      ["the", "site"],
    ],
    ["an escaped percent is text, not a comment", "50\\% teh", ["teh"]],
  ])("%s", (_name, text, expected) => {
    expect(words(text)).toEqual(expected);
  });
});

describe("checkableWords: what is skipped", () => {
  it.each([
    ["the document class and its name", "\\documentclass[12pt]{artcle}"],
    ["a package name", "\\usepackage[utf8]{inputenc}"],
    ["inline math", "$\\alpha$ $x = teh$"],
    ["display math", "$$teh + wrold$$"],
    ["parenthesis math", "\\(teh\\)"],
    ["bracket math", "\\[teh\\]"],
    ["a math environment", "\\begin{equation}teh\\end{equation}"],
    ["a starred math environment", "\\begin{align*}teh\\end{align*}"],
    ["a comment", "% a teh comment"],
    ["a verbatim environment", "\\begin{verbatim}teh\\end{verbatim}"],
    ["an inline verb", "\\verb|teh|"],
    ["a citation key", "\\cite[p.~3]{smith2020teh}"],
    ["a reference label", "\\ref{fig:teh}\\label{sec:wrold}"],
    ["a cross reference", "\\cref{sec:teh} \\eqref{eq:wrold}"],
    ["a file path", "\\input{chapters/teh} \\include{wrold}"],
    ["an image path and its options", "\\includegraphics[width=teh]{figures/teh}"],
    ["a url", "\\url{https://teh.example/wrold}"],
    ["begin and end arguments", "\\begin{tikzpicture}[scale=2]\\end{tikzpicture}"],
    ["a tabular column specification", "\\begin{tabular}{llr}"],
    ["a control word with no argument", "\\newline\\par"],
  ])("skips %s", (_name, text) => {
    expect(words(text)).toEqual([]);
  });

  it("skips a comment but not the next line", () => {
    expect(words("% teh\nwrold")).toEqual(["wrold"]);
  });

  it("resumes checking after an inline math span", () => {
    expect(words("a $teh$ wrold")).toEqual(["wrold"]);
  });

  it("ends an unclosed dollar at the blank line", () => {
    expect(words("$teh\n\nwrold")).toEqual(["wrold"]);
  });

  it("skips words with digits", () => {
    expect(words("COVID19 and 2pt and mp3")).toEqual(["and", "and"]);
  });

  it("skips all-caps words of up to five letters", () => {
    expect(words("NASA IEEE TEHNOLOGY")).toEqual(["TEHNOLOGY"]);
  });

  it("does not check one-letter words", () => {
    expect(words("a b I")).toEqual([]);
  });

  it("skips contractions and elisions", () => {
    expect(words("don't d'água l’homme")).toEqual([]);
  });
});

describe("checkableWords: ranges", () => {
  it("returns only the words that overlap the requested range", () => {
    const text = "alpha beta gamma";
    const hits = checkableWords(text, 6, 10).map((w) => w.word);
    expect(hits).toEqual(["beta"]);
  });

  it("reports offsets into the full text", () => {
    const text = "one \\emph{two}";
    expect(checkableWords(text, 0, text.length)).toEqual([
      { from: 0, to: 3, word: "one" },
      { from: 10, to: 13, word: "two" },
    ]);
  });

  it("keeps a word that the range cuts through", () => {
    const text = "wonderful";
    expect(checkableWords(text, 0, 4)).toEqual([{ from: 0, to: 9, word: "wonderful" }]);
  });
});
