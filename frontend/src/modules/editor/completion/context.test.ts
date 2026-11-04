import { CompletionContext } from "@codemirror/autocomplete";
import { EditorState } from "@codemirror/state";
import { describe, expect, it } from "vitest";

import { argumentToken, commandToken, environmentToken, ignoredAt, inComment, inVerbatim } from "./context";

/** A context whose cursor sits where the `▮` marker is. */
function contextAt(doc: string, explicit = false): CompletionContext {
  const pos = doc.indexOf("▮");
  const state = EditorState.create({ doc: doc.replace("▮", "") });
  return new CompletionContext(state, pos, explicit);
}

describe("comments", () => {
  it.each([
    ["% a comment", true],
    ["text % a comment", true],
    ["50\\% of the text", false],
    ["\\\\ then a comment %", true],
    ["plain text", false],
    ["", false],
  ])("inComment(%j) is %s", (line, expected) => {
    expect(inComment(line)).toBe(expected);
  });

  it("is silent at the cursor of a comment and speaks again after it", () => {
    expect(ignoredAt(contextAt("% \\sec▮"))).toBe(true);
    expect(ignoredAt(contextAt("\\sec▮ % later"))).toBe(false);
    expect(ignoredAt(contextAt("% first line\n\\sec▮"))).toBe(false);
  });
});

describe("verbatim environments", () => {
  it.each([
    ["\\begin{verbatim}\n\\sec", true],
    ["\\begin{lstlisting}\n\\sec", true],
    ["\\begin{verbatim}\nx\n\\end{verbatim}\n\\sec", false],
    ["\\begin{verbatim}\n\\begin{comment}\n", true],
    ["\\begin{comment}\nhidden\n\\end{comment}\n", false],
    ["\\begin{itemize}\n\\sec", false],
  ])("inVerbatim(%j) is %s", (text, expected) => {
    expect(inVerbatim(text)).toBe(expected);
  });

  it("is silent inside a verbatim block", () => {
    expect(ignoredAt(contextAt("\\begin{verbatim}\n\\sec▮"))).toBe(true);
    expect(ignoredAt(contextAt("\\begin{verbatim}x\\end{verbatim}\n\\sec▮"))).toBe(false);
  });
});

describe("tokens", () => {
  it("reads a command typed after a backslash", () => {
    expect(commandToken(contextAt("text \\sec▮"))).toEqual({ from: 5, text: "\\sec" });
    expect(commandToken(contextAt("text ▮"))).toBeNull();
  });

  it("reads the name after \\begin{, starting at the name", () => {
    expect(environmentToken(contextAt("\\begin{fig▮"))).toEqual({ from: 7, text: "fig" });
    expect(environmentToken(contextAt("\\begin{▮"))).toEqual({ from: 7, text: "" });
    expect(environmentToken(contextAt("\\end{fig▮"))).toBeNull();
  });

  it("reads the item after the last comma of a citation list", () => {
    const cite = ["cite"];
    expect(argumentToken(contextAt("\\cite{si▮"), cite)).toEqual({ from: 6, text: "si" });
    expect(argumentToken(contextAt("\\cite{silva2023, ▮"), cite)).toEqual({ from: 17, text: "" });
    expect(argumentToken(contextAt("\\cite{silva2023,so▮"), cite)).toEqual({ from: 16, text: "so" });
  });

  it("skips an optional argument and ignores other commands", () => {
    expect(argumentToken(contextAt("\\cite[p.~5]{ab▮"), ["cite"])).toEqual({ from: 12, text: "ab" });
    expect(argumentToken(contextAt("\\cite{ab▮"), ["ref"])).toBeNull();
    expect(argumentToken(contextAt("\\cite{ab}▮"), ["cite"])).toBeNull();
  });
});
