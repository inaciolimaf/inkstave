import { describe, expect, it } from "vitest";

import { parseBib } from "./parse-bib";

describe("parseBib", () => {
  it("reads the key, type, title, author and year of an entry", () => {
    const [entry] = parseBib("@article{silva2023, title={Deep}, author={Silva, A.}, year={2023}}");
    expect(entry).toEqual({
      key: "silva2023",
      type: "article",
      title: "Deep",
      author: "Silva, A.",
      year: "2023",
    });
  });

  it("accepts quoted values, bare years, and values joined with #", () => {
    const text = `@book{k1, title = "Quoted title", year = 2001}
@book{k2, author = "Silva, A." # " and Souza, B.", year = {2010}}`;
    expect(parseBib(text)).toEqual([
      { key: "k1", type: "book", title: "Quoted title", year: "2001" },
      { key: "k2", type: "book", author: "Silva, A. and Souza, B.", year: "2010" },
    ]);
  });

  it("drops one outer brace level and collapses whitespace in titles", () => {
    const [entry] = parseBib("@misc{k, title={{The  Big\n  Question}}}");
    expect(entry.title).toBe("The Big Question");
    const [plain] = parseBib("@misc{k, title={The {GPU} era}}");
    expect(plain.title).toBe("The {GPU} era");
  });

  it("keeps LaTeX accents as typed", () => {
    const [entry] = parseBib('@misc{k, author={M{\\"u}ller, Jo}}');
    expect(entry.author).toBe('M{\\"u}ller, Jo');
  });

  it("skips comment, string and preamble entries with their bodies", () => {
    const text = `@comment{@article{ghost, title={Not real}}}
@string{jan = "January"}
@preamble{"\\newcommand{\\x}{}"}
@article{real, title={Real}}`;
    expect(parseBib(text).map((entry) => entry.key)).toEqual(["real"]);
  });

  it("returns the entries in file order and without optional fields that are absent", () => {
    const entries = parseBib("@misc{first}\n@misc{second, year={}}");
    expect(entries).toEqual([
      { key: "first", type: "misc" },
      { key: "second", type: "misc" },
    ]);
  });

  it("lowercases the entry type and the field names", () => {
    const [entry] = parseBib("@ARTICLE{k, TITLE={Upper}}");
    expect(entry).toEqual({ key: "k", type: "article", title: "Upper" });
  });

  it("skips a malformed entry and keeps reading the next one", () => {
    const text = `@article{broken, title={never closed
@article{ok, title={Fine}}
@article{with space, title={Bad key}}
@article{, title={No key}}
@article{after, title={Also fine}}`;
    const keys = parseBib(text).map((entry) => entry.key);
    expect(keys).toContain("after");
    expect(keys).not.toContain("with space");
    expect(keys).not.toContain("");
  });

  it.each([
    "",
    "no entries at all",
    "@",
    "@article",
    "@article{",
    "@article{k, title={",
    "@article{k, title=}",
    "@article{k, = 3}",
    "}}}{{{",
    '@article{k, title="unclosed',
    "@article{k, year=2023 # }",
  ])("never throws on %j", (text) => {
    expect(() => parseBib(text)).not.toThrow();
  });

  it("keeps the readable entries of a half-typed file", () => {
    const text = "@article{good, title={Good}}\n@article{half, title={Half typed";
    expect(parseBib(text)).toEqual([{ key: "good", type: "article", title: "Good" }]);
  });
});
