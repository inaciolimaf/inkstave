/** The rules of spec 119 §5.2, one case each, against the planner's operations. */
import { describe, expect, it } from "vitest";

import { SUGGESTION_TEXT_MAX_CHARS } from "./model";
import { type PlanInput, type TextChange, planEdit } from "./record";

const AUTHOR = { id: "b", name: "B" };
const NOW = "2026-11-04T10:00:00.000Z";
const OLD_CREATED = "2026-11-04T09:00:00.000Z";

const OLD = "the very old important point, with more words here";

function plan(
  oldText: string,
  changes: TextChange[],
  options: Partial<Pick<PlanInput, "own" | "author">> = {},
) {
  let counter = 0;
  return planEdit({
    changes,
    own: options.own ?? [],
    author: options.author === undefined ? AUTHOR : options.author,
    now: NOW,
    newId: () => `N${++counter}`,
    removed: (from, to) => oldText.slice(from, to),
  });
}

describe("planEdit: insertions (spec 119 §5.2)", () => {
  it("types elsewhere: a new insertion over the typed text", () => {
    expect(plan(OLD, [{ from: 4, to: 4, insert: "very " }])).toEqual({
      blocked: false,
      ops: [
        { kind: "text-insert", at: 4, text: "very " },
        { kind: "insertion-set", id: "N1", from: 4, to: 9, createdAt: NOW },
      ],
    });
  });

  it("types next to the end of its own open insertion: the insertion grows", () => {
    const result = plan(OLD, [{ from: 9, to: 9, insert: "!" }], {
      own: [{ id: "a", from: 4, to: 9, createdAt: OLD_CREATED }],
    });
    expect(result.ops).toEqual([
      { kind: "text-insert", at: 9, text: "!" },
      { kind: "insertion-set", id: "a", from: 4, to: 10, createdAt: OLD_CREATED },
    ]);
  });

  it("types at the start of its own insertion: the insertion grows from there", () => {
    const result = plan(OLD, [{ from: 4, to: 4, insert: "x" }], {
      own: [{ id: "a", from: 4, to: 9, createdAt: NOW }],
    });
    expect(result.ops).toEqual([
      { kind: "text-insert", at: 4, text: "x" },
      { kind: "insertion-set", id: "a", from: 4, to: 10, createdAt: NOW },
    ]);
  });

  it("types inside its own insertion: the insertion grows, and no second record is made", () => {
    const result = plan(OLD, [{ from: 6, to: 6, insert: "y" }], {
      own: [{ id: "a", from: 4, to: 9, createdAt: NOW }],
    });
    expect(result.ops).toEqual([
      { kind: "text-insert", at: 6, text: "y" },
      { kind: "insertion-set", id: "a", from: 4, to: 10, createdAt: NOW },
    ]);
  });

  it("an insertion before an own one leaves that one in place and gets its own record", () => {
    const result = plan(OLD, [{ from: 0, to: 0, insert: "A" }], {
      own: [{ id: "a", from: 4, to: 9, createdAt: NOW }],
    });
    expect(result.ops).toEqual([
      { kind: "text-insert", at: 0, text: "A" },
      { kind: "insertion-set", id: "N1", from: 0, to: 1, createdAt: NOW },
    ]);
  });

  it("a later change in the same edit lands where the earlier one moved the text to", () => {
    const result = plan(
      OLD,
      [
        { from: 0, to: 0, insert: "A" },
        { from: 10, to: 10, insert: "B" },
      ],
      { own: [{ id: "a", from: 4, to: 9, createdAt: NOW }] },
    );
    // The first change shifts the own insertion to 5..10. Old position 10 is now 11, outside it.
    expect(result.ops).toEqual([
      { kind: "text-insert", at: 0, text: "A" },
      { kind: "insertion-set", id: "N1", from: 0, to: 1, createdAt: NOW },
      { kind: "text-insert", at: 11, text: "B" },
      { kind: "insertion-set", id: "N2", from: 11, to: 12, createdAt: NOW },
    ]);
  });
});

describe("planEdit: deletions (spec 119 §5.2)", () => {
  it("deletes text that is not its own: a deletion record with the removed text", () => {
    expect(plan(OLD, [{ from: 0, to: 3, insert: "" }]).ops).toEqual([
      { kind: "text-delete", from: 0, to: 3 },
      { kind: "deletion-add", id: "N1", at: 0, text: "the" },
    ]);
  });

  it("deletes inside its own insertion: the text goes, the insertion shrinks, no deletion record", () => {
    const result = plan(OLD, [{ from: 5, to: 7, insert: "" }], {
      own: [{ id: "a", from: 4, to: 9, createdAt: NOW }],
    });
    expect(result.ops).toEqual([
      { kind: "text-delete", from: 5, to: 7 },
      { kind: "insertion-set", id: "a", from: 4, to: 7, createdAt: NOW },
    ]);
  });

  it("deletes its whole own insertion: the record goes and nothing is recorded as deleted", () => {
    const result = plan(OLD, [{ from: 4, to: 9, insert: "" }], {
      own: [{ id: "a", from: 4, to: 9, createdAt: NOW }],
    });
    expect(result.ops).toEqual([
      { kind: "text-delete", from: 4, to: 9 },
      { kind: "insertion-remove", id: "a" },
    ]);
  });

  it("deletes across its own insertion and other text: the own part goes, the rest is recorded", () => {
    // "aaaa BBBB cccc": the own insertion is BBBB at 5..9. Old 2..11 is "aa BBBB c"; the parts outside the
    // own insertion are "aa " (2..5) and " c" (9..11), which together are the recorded text.
    const result = plan("aaaa BBBB cccc", [{ from: 2, to: 11, insert: "" }], {
      own: [{ id: "a", from: 5, to: 9, createdAt: NOW }],
    });
    expect(result.ops).toEqual([
      { kind: "text-delete", from: 2, to: 11 },
      { kind: "insertion-remove", id: "a" },
      { kind: "deletion-add", id: "N1", at: 2, text: "aa  c" },
    ]);
  });

  it("a replacement of other text: the deletion is recorded, then the new text is an insertion", () => {
    expect(plan(OLD, [{ from: 4, to: 8, insert: "new" }]).ops).toEqual([
      { kind: "text-delete", from: 4, to: 8 },
      { kind: "deletion-add", id: "N1", at: 4, text: "very" },
      { kind: "text-insert", at: 4, text: "new" },
      { kind: "insertion-set", id: "N2", from: 4, to: 7, createdAt: NOW },
    ]);
  });

  it("blocks a deletion of more than 100 000 characters", () => {
    const text = "x".repeat(SUGGESTION_TEXT_MAX_CHARS + 1);
    expect(plan(text, [{ from: 0, to: text.length, insert: "" }])).toEqual({ ops: [], blocked: true });
  });

  it("allows a deletion of exactly 100 000 characters", () => {
    const text = "x".repeat(SUGGESTION_TEXT_MAX_CHARS);
    expect(plan(text, [{ from: 0, to: text.length, insert: "" }]).blocked).toBe(false);
  });
});

describe("planEdit: edits with Suggesting off", () => {
  it("is a plain edit: text operations only, even inside someone's suggestion", () => {
    const result = plan(
      OLD,
      [
        { from: 5, to: 7, insert: "" },
        { from: 9, to: 9, insert: "Z" },
      ],
      {
        author: null,
        own: [{ id: "a", from: 4, to: 9, createdAt: NOW }],
      },
    );
    expect(result.ops).toEqual([
      { kind: "text-delete", from: 5, to: 7 },
      { kind: "text-insert", at: 7, text: "Z" },
    ]);
    expect(result.blocked).toBe(false);
  });

  it("does not refuse a large deletion when Suggesting is off", () => {
    const text = "x".repeat(SUGGESTION_TEXT_MAX_CHARS + 5);
    const result = plan(text, [{ from: 0, to: text.length, insert: "" }], { author: null });
    expect(result).toEqual({ ops: [{ kind: "text-delete", from: 0, to: text.length }], blocked: false });
  });
});
