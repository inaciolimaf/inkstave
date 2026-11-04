/** Accept and reject on a Y.Text (spec 119 §5.4). */
import { describe, expect, it } from "vitest";
import * as Y from "yjs";

import { REVIEW_ORIGIN, decideAllSuggestions, decideSuggestion } from "./review";
import { type SuggestionFields, encodePosition, readSuggestions } from "./model";

const WHEN = "2026-11-04T10:00:00.000Z";

function setup(initial: string) {
  const doc = new Y.Doc();
  const text = doc.getText("content");
  const map = doc.getMap<SuggestionFields>("suggestions");
  text.insert(0, initial);
  return { doc, text, map };
}

/** Records an insertion of `from`..`to` by B, and a deletion of `removed` at `at`. */
function insertionOf(text: Y.Text, from: number, to: number): SuggestionFields {
  return {
    kind: "insert",
    author_id: "b",
    author_name: "B",
    created_at: WHEN,
    start: encodePosition(text, from, 0),
    end: encodePosition(text, to, -1),
  };
}

function deletionAt(text: Y.Text, at: number, removed: string): SuggestionFields {
  return {
    kind: "delete",
    author_id: "b",
    author_name: "B",
    created_at: WHEN,
    at: encodePosition(text, at, 0),
    text: removed,
  };
}

describe("decideSuggestion", () => {
  it("accepting an insertion drops the record and keeps the text", () => {
    const { doc, text, map } = setup("hello very important world");
    map.set("s1", insertionOf(text, 5, 20));
    expect(decideSuggestion(text, map, "s1", "accept")).toBe(true);
    expect(text.toString()).toBe("hello very important world");
    expect(map.size).toBe(0);
    doc.destroy();
  });

  it("rejecting an insertion removes its text and the record", () => {
    const { doc, text, map } = setup("hello very important world");
    map.set("s1", insertionOf(text, 5, 20));
    decideSuggestion(text, map, "s1", "reject");
    expect(text.toString()).toBe("hello world");
    expect(map.size).toBe(0);
    doc.destroy();
  });

  it("rejecting a deletion puts back exactly the removed text, where it was", () => {
    const { doc, text, map } = setup("hello world");
    map.set("s2", deletionAt(text, 6, "old "));
    decideSuggestion(text, map, "s2", "reject");
    expect(text.toString()).toBe("hello old world");
    expect(map.size).toBe(0);
    doc.destroy();
  });

  it("accepting a deletion drops the record and leaves the text without it", () => {
    const { doc, text, map } = setup("hello world");
    map.set("s2", deletionAt(text, 6, "old "));
    decideSuggestion(text, map, "s2", "accept");
    expect(text.toString()).toBe("hello world");
    expect(map.size).toBe(0);
    doc.destroy();
  });

  it("refuses to reject a suggestion whose place is gone, and dismisses it instead", () => {
    const { doc, text, map } = setup("hello world");
    map.set("s1", insertionOf(text, 0, 5));
    text.delete(0, 5);
    // The text is gone, so the insertion is now empty: it reads as stale and cannot be rejected.
    expect(readSuggestions(text, map)[0].range).toBeNull();
    expect(decideSuggestion(text, map, "s1", "reject")).toBe(false);
    expect(decideSuggestion(text, map, "s1", "accept")).toBe(true);
    expect(map.size).toBe(0);
    doc.destroy();
  });

  it("writes its change with the review origin, so no one's undo takes it back", () => {
    const { doc, text, map } = setup("hello world");
    map.set("s2", deletionAt(text, 6, "old "));
    const origins: unknown[] = [];
    doc.on("afterTransaction", (transaction: Y.Transaction) => origins.push(transaction.origin));
    decideSuggestion(text, map, "s2", "reject");
    expect(origins).toEqual([REVIEW_ORIGIN]);
    doc.destroy();
  });
});

describe("decideAllSuggestions", () => {
  it("rejects every suggestion in one transaction, each at its resolved place", () => {
    const { doc, text, map } = setup("hello very important world");
    map.set("ins", insertionOf(text, 5, 20));
    map.set("del", deletionAt(text, 21, "old "));
    let transactions = 0;
    doc.on("afterTransaction", () => {
      transactions += 1;
    });
    expect(decideAllSuggestions(text, map, "reject")).toBe(2);
    expect(transactions).toBe(1);
    expect(text.toString()).toBe("hello old world");
    expect(map.size).toBe(0);
    doc.destroy();
  });

  it("accepts every suggestion, keeping the text", () => {
    const { doc, text, map } = setup("hello very world");
    map.set("ins", insertionOf(text, 6, 10));
    map.set("del", deletionAt(text, 11, "old "));
    expect(decideAllSuggestions(text, map, "accept")).toBe(2);
    expect(text.toString()).toBe("hello very world");
    expect(map.size).toBe(0);
    doc.destroy();
  });
});
