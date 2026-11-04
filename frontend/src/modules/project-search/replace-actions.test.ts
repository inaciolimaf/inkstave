import { describe, expect, it, vi } from "vitest";

import { findMatches } from "./find";
import { applyEdits } from "./replace";
import { type TextWriter, StaleMatchError, replaceInFiles, replaceMatch } from "./replace-actions";

/** A writer over plain strings, standing in for the live documents. */
function fakeWriter(texts: Record<string, string>): TextWriter & { texts: Record<string, string> } {
  return {
    texts,
    async transformContent(path, edit) {
      const current = texts[path];
      if (current === undefined) return null;
      texts[path] = applyEdits(current, edit(current));
      return texts[path];
    },
  };
}

const query = { pattern: /rede neural/g, replacement: "modelo neural", regex: false };

describe("replaceMatch", () => {
  it("replaces only the chosen match, on the live text", async () => {
    const writer = fakeWriter({ "a.tex": "rede neural\nrede neural\n" });
    const seen = findMatches("rede neural\nrede neural\n", query.pattern);
    const file = { docId: "a", path: "a.tex", matches: seen };
    // A collaborator added a line above since the search ran.
    writer.texts["a.tex"] = "Intro\nrede neural\nrede neural\n";
    await replaceMatch(writer, file, seen[1], query);
    expect(writer.texts["a.tex"]).toBe("Intro\nrede neural\nmodelo neural\n");
  });

  it("writes nothing when the match's line changed", async () => {
    const writer = fakeWriter({ "a.tex": "rede neural\n" });
    const seen = findMatches("rede neural\n", query.pattern);
    writer.texts["a.tex"] = "a rede neural\n";
    await expect(
      replaceMatch(writer, { docId: "a", path: "a.tex", matches: seen }, seen[0], query),
    ).rejects.toBeInstanceOf(StaleMatchError);
    expect(writer.texts["a.tex"]).toBe("a rede neural\n");
  });
});

describe("replaceInFiles", () => {
  it("replaces every match of every file and reports what it changed", async () => {
    const writer = fakeWriter({ "a.tex": "rede neural x rede neural", "b.tex": "uma rede neural" });
    const onWritten = vi.fn();
    const outcome = await replaceInFiles(
      writer,
      [
        { docId: "a", path: "a.tex" },
        { docId: "b", path: "b.tex" },
        { docId: "gone", path: "gone.tex" },
      ],
      query,
      onWritten,
    );
    expect(writer.texts).toEqual({ "a.tex": "modelo neural x modelo neural", "b.tex": "uma modelo neural" });
    expect(outcome).toEqual({ replaced: 3, files: 2, failed: ["gone.tex"] });
    expect(onWritten).toHaveBeenCalledWith("b", "uma modelo neural");
  });
});
