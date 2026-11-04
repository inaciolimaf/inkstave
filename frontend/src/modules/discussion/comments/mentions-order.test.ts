import { describe, expect, it } from "vitest";

import type { CommentThread } from "./api";
import { insertMention, mentionIds, mentionQuery, matchingMembers } from "./mentions";
import { orderThreads } from "./order";

const ANA = { id: "u-ana", name: "Ana" };
const BEN = { id: "u-ben", name: "Ben Lee" };

describe("mentions", () => {
  it("keeps only the picks whose @Name is still in the text", () => {
    expect(mentionIds("@Ana please, and @Ben Lee too", [ANA, BEN])).toEqual(["u-ana", "u-ben"]);
    expect(mentionIds("Ana, please", [ANA])).toEqual([]);
  });

  it("reads the @ word right before the caret", () => {
    expect(mentionQuery("hi @an", 6)).toEqual({ start: 3, query: "an" });
    expect(mentionQuery("hi @", 4)).toEqual({ start: 3, query: "" });
    expect(mentionQuery("mail me@x", 9)).toBeNull();
    expect(mentionQuery("hi @an", 3)).toBeNull();
  });

  it("replaces the query with the full name and moves the caret after it", () => {
    expect(insertMention("hi @an", 6, 3, "Ana")).toEqual({ value: "hi @Ana ", caret: 8 });
  });

  it("lists names that start with the query first", () => {
    const members = [{ id: "1", name: "Lia Ana" }, ANA, BEN];
    expect(matchingMembers(members, "an").map((m) => m.name)).toEqual(["Ana", "Lia Ana"]);
  });
});

function thread(id: string, documentId: string, createdAt: string, resolved = false): CommentThread {
  return {
    id,
    document_id: documentId,
    anchor_start: "",
    anchor_end: "",
    quoted_text: "q",
    author: null,
    created_at: createdAt,
    resolved_at: resolved ? createdAt : null,
    resolved_by: null,
    messages: [],
  } as unknown as CommentThread;
}

describe("comment order", () => {
  const threads = [
    thread("other", "doc-b", "2026-01-01T00:00:00Z"),
    thread("late", "doc-a", "2026-01-03T00:00:00Z"),
    thread("early", "doc-a", "2026-01-02T00:00:00Z"),
    thread("gone", "doc-a", "2026-01-04T00:00:00Z"),
    thread("done", "doc-a", "2026-01-05T00:00:00Z", true),
  ];
  const ranges = new Map([
    ["late", { from: 40, to: 50 }],
    ["early", { from: 5, to: 9 }],
    ["gone", null],
    ["done", { from: 1, to: 2 }],
  ]);
  const base = {
    currentDocumentId: "doc-a",
    ranges,
    fileName: (id: string) => (id === "doc-a" ? "main.tex" : "refs.tex"),
  };

  it("lists the open document in text order, detached last, then the other files", () => {
    const rows = orderThreads(threads, { ...base, filter: "open", scope: "all" });
    expect(rows.map((r) => r.thread.id)).toEqual(["early", "late", "gone", "other"]);
  });

  it("shows only the open document when the scope is this file", () => {
    const rows = orderThreads(threads, { ...base, filter: "open", scope: "file" });
    expect(rows.map((r) => r.thread.id)).toEqual(["early", "late", "gone"]);
  });

  it("filters by status", () => {
    expect(
      orderThreads(threads, { ...base, filter: "resolved", scope: "all" }).map((r) => r.thread.id),
    ).toEqual(["done"]);
    expect(orderThreads(threads, { ...base, filter: "all", scope: "all" })).toHaveLength(5);
  });
});
