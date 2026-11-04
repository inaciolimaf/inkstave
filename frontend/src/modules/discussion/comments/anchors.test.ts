/**
 * Anchors across two Y.Docs that exchange updates (spec 118, acceptance criteria 1, 2 and 6). The
 * anchors are created on one peer and must resolve to the same text on the other, whatever the
 * other peer inserted or deleted in the meantime.
 */
import * as Y from "yjs";
import { describe, expect, it } from "vitest";

import { encodeAnchor, resolveAnchor } from "./anchors";

function peers(initial: string) {
  const a = new Y.Doc();
  const b = new Y.Doc();
  a.getText("content").insert(0, initial);
  Y.applyUpdate(b, Y.encodeStateAsUpdate(a));
  const sync = () => {
    Y.applyUpdate(b, Y.encodeStateAsUpdate(a));
    Y.applyUpdate(a, Y.encodeStateAsUpdate(b));
  };
  return { a, b, sync, ta: a.getText("content"), tb: b.getText("content") };
}

/** The text that a range resolves to on a peer. */
function selected(text: Y.Text, anchors: { anchorStart: string; anchorEnd: string }): string | null {
  const range = resolveAnchor(text, anchors.anchorStart, anchors.anchorEnd);
  return range ? text.toString().slice(range.from, range.to) : null;
}

const BODY = "Intro.\n\nFirst paragraph.\n\nWe read the results and they were clear.\n";

describe("comment anchors", () => {
  it("keeps the highlight on its text when the other peer inserts before it (AC 1)", () => {
    const { ta, tb, sync } = peers(BODY);
    const from = BODY.indexOf("the results");
    const anchors = encodeAnchor(ta, from, from + "the results".length);

    tb.insert(0, "A new sentence before everything. ");
    sync();

    expect(selected(ta, anchors)).toBe("the results");
    expect(selected(tb, anchors)).toBe("the results");
  });

  it("does not pull text typed at the very end of the range into it (AC 2)", () => {
    const { ta, tb, sync } = peers(BODY);
    const from = BODY.indexOf("the results");
    const to = from + "the results".length;
    const anchors = encodeAnchor(ta, from, to);

    tb.insert(to, " with more");
    sync();

    expect(selected(ta, anchors)).toBe("the results");
    expect(selected(tb, anchors)).toBe("the results");
  });

  it("does not pull text typed at the very start of the range into it", () => {
    const { ta, tb, sync } = peers(BODY);
    const from = BODY.indexOf("the results");
    const anchors = encodeAnchor(ta, from, from + "the results".length);

    tb.insert(from, "very ");
    sync();

    expect(selected(ta, anchors)).toBe("the results");
  });

  it("detaches when the whole commented text is deleted, and never jumps elsewhere (AC 6)", () => {
    const { ta, tb, sync } = peers(BODY);
    const from = BODY.indexOf("the results");
    const anchors = encodeAnchor(ta, from, from + "the results".length);

    tb.delete(from, "the results".length);
    sync();

    expect(resolveAnchor(ta, anchors.anchorStart, anchors.anchorEnd)).toBeNull();
    expect(resolveAnchor(tb, anchors.anchorStart, anchors.anchorEnd)).toBeNull();
  });

  it("follows an edit inside the range", () => {
    const { ta, tb, sync } = peers(BODY);
    const from = BODY.indexOf("the results");
    const anchors = encodeAnchor(ta, from, from + "the results".length);

    tb.insert(from + 4, "final ");
    sync();

    expect(selected(ta, anchors)).toBe("the final results");
  });

  it("returns null for an anchor that cannot be read", () => {
    const { ta } = peers(BODY);
    expect(resolveAnchor(ta, "not base64 at all!", "AAAA")).toBeNull();
    expect(resolveAnchor(ta, "AAAA", "AAAA")).toBeNull();
  });
});
