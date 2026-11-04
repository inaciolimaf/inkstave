/** Positions of the suggestions survive concurrent edits on two peers (spec 119 §8). */
import { describe, expect, it } from "vitest";
import * as Y from "yjs";

import {
  type SuggestionFields,
  type SuggestionMap,
  encodePosition,
  newSuggestionId,
  readSuggestions,
  resolveSuggestion,
} from "./model";

function peer(): { doc: Y.Doc; text: Y.Text; map: SuggestionMap } {
  const doc = new Y.Doc();
  return { doc, text: doc.getText("content"), map: doc.getMap<SuggestionFields>("suggestions") };
}

function sync(a: Y.Doc, b: Y.Doc): void {
  Y.applyUpdate(b, Y.encodeStateAsUpdate(a, Y.encodeStateVector(b)));
  Y.applyUpdate(a, Y.encodeStateAsUpdate(b, Y.encodeStateVector(a)));
}

function insertion(text: Y.Text, from: number, to: number): SuggestionFields {
  return {
    kind: "insert",
    author_id: "b",
    author_name: "B",
    created_at: "2026-11-04T10:00:00.000Z",
    start: encodePosition(text, from, 0),
    end: encodePosition(text, to, -1),
  };
}

describe("newSuggestionId", () => {
  it("is a UUID version 7 and sorts by creation time", () => {
    const earlier = newSuggestionId(1_700_000_000_000);
    const later = newSuggestionId(1_700_000_005_000);
    expect(earlier).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(earlier < later).toBe(true);
  });
});

describe("suggestion positions", () => {
  it("follow the text when two peers edit it concurrently", () => {
    const a = peer();
    const b = peer();
    a.text.insert(0, "hello world");
    sync(a.doc, b.doc);

    // A suggests "world" (6..11) while B inserts "big " at the start, at the same time.
    a.map.set("s1", insertion(a.text, 6, 11));
    b.text.insert(0, "big ");
    sync(a.doc, b.doc);

    for (const { text, map } of [a, b]) {
      const [placed] = readSuggestions(text, map);
      expect(placed.range).toEqual({ from: 10, to: 15 });
      expect(text.toString().slice(10, 15)).toBe("world");
    }
  });

  it("an insertion moves with the text before it, and takes in text typed inside it", () => {
    const a = peer();
    a.text.insert(0, "hello world");
    a.map.set("s1", insertion(a.text, 6, 11));
    a.text.insert(0, "oh, ");
    expect(resolveSuggestion(a.text, a.map.get("s1")!)).toEqual({ from: 10, to: 15 });
    a.text.insert(12, "X");
    expect(resolveSuggestion(a.text, a.map.get("s1")!)).toEqual({ from: 10, to: 16 });
  });

  it("a deletion marker stays at its place after the text around it changes", () => {
    const a = peer();
    a.text.insert(0, "hello world");
    a.map.set("s2", {
      kind: "delete",
      author_id: "b",
      author_name: "B",
      created_at: "2026-11-04T10:00:00.000Z",
      at: encodePosition(a.text, 6, 0),
      text: "old ",
    });
    a.text.insert(0, "x");
    expect(resolveSuggestion(a.text, a.map.get("s2")!)).toEqual({ from: 7, to: 7 });
  });

  it("an emptied insertion has no range and sorts last", () => {
    const a = peer();
    a.text.insert(0, "hello world");
    a.map.set("early", insertion(a.text, 0, 5));
    a.map.set("late", insertion(a.text, 6, 11));
    a.text.delete(0, 5);
    const placed = readSuggestions(a.text, a.map);
    expect(placed.map((p) => p.suggestion.id)).toEqual(["late", "early"]);
    expect(placed[1].range).toBeNull();
  });

  it("a malformed position resolves to null instead of throwing", () => {
    const a = peer();
    a.text.insert(0, "abc");
    const malformed = { ...insertion(a.text, 0, 1), start: "%%%" } as SuggestionFields;
    expect(resolveSuggestion(a.text, malformed)).toBeNull();
  });
});
