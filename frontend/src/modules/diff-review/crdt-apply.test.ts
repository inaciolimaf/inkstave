import { describe, expect, it } from "vitest";
import * as Y from "yjs";

import {
  AGENT_APPLY_ORIGIN,
  SEARCH_REPLACE_ORIGIN,
  applySplicesToYText,
  applyTargetToYText,
  createYDocBridge,
} from "./crdt-apply";

describe("applyTargetToYText", () => {
  it("writes the target as a minimal, origin-tagged edit (AC5)", () => {
    const doc = new Y.Doc();
    const text = doc.getText("content");
    text.insert(0, "a\nb\nc\n");

    let origin: unknown = null;
    doc.on("update", (_u: Uint8Array, o: unknown) => {
      origin = o;
    });
    applyTargetToYText(text, "a\nB\nc\n");

    expect(text.toString()).toBe("a\nB\nc\n");
    expect(origin).toBe(AGENT_APPLY_ORIGIN);
  });

  it("is a no-op when target equals current", () => {
    const doc = new Y.Doc();
    const text = doc.getText("content");
    text.insert(0, "same\n");
    let updated = false;
    doc.on("update", () => {
      updated = true;
    });
    applyTargetToYText(text, "same\n");
    expect(updated).toBe(false);
  });

  it("converges collaborators and preserves an unrelated concurrent edit (AC6)", () => {
    const a = new Y.Doc();
    const b = new Y.Doc();
    a.getText("content").insert(0, "a\nb\nc\n");
    Y.applyUpdate(b, Y.encodeStateAsUpdate(a)); // b syncs to a

    // Collaborator B edits the (unrelated) first line before sync.
    b.getText("content").delete(0, 1);
    b.getText("content").insert(0, "A");

    // The agent apply on A changes only the middle line.
    applyTargetToYText(a.getText("content"), "a\nB\nc\n");

    // Exchange updates both ways.
    Y.applyUpdate(b, Y.encodeStateAsUpdate(a));
    Y.applyUpdate(a, Y.encodeStateAsUpdate(b));

    expect(a.getText("content").toString()).toBe(b.getText("content").toString());
    expect(a.getText("content").toString()).toBe("A\nB\nc\n"); // both edits preserved
  });
});

describe("createYDocBridge", () => {
  it("reads seeded content and applies a target", async () => {
    const bridge = createYDocBridge({ "main.tex": "x\ny\n" });
    expect(await bridge.readContent("main.tex")).toBe("x\ny\n");
    await bridge.applyContent("main.tex", "x\nY\n");
    expect(bridge.getText("main.tex").toString()).toBe("x\nY\n");
  });
});

describe("applySplicesToYText", () => {
  it("writes every splice in one origin-tagged transaction", () => {
    const doc = new Y.Doc();
    const text = doc.getText("content");
    text.insert(0, "net a net b net");
    const origins: unknown[] = [];
    doc.on("update", (_u: Uint8Array, o: unknown) => origins.push(o));
    applySplicesToYText(text, [
      { from: 0, to: 3, insert: "NET" },
      { from: 12, to: 15, insert: "NET" },
      { from: 6, to: 9, insert: "NET" },
    ]);
    expect(text.toString()).toBe("NET a NET b NET");
    expect(origins).toEqual([SEARCH_REPLACE_ORIGIN]);
  });

  it("keeps a collaborator's edit between two replaced matches (spec 122)", () => {
    const a = new Y.Doc();
    const b = new Y.Doc();
    a.getText("content").insert(0, "net\nmiddle\nnet\n");
    Y.applyUpdate(b, Y.encodeStateAsUpdate(a));
    // B types in the middle line while A replaces both matches around it.
    b.getText("content").insert(4, "typed ");
    applySplicesToYText(a.getText("content"), [
      { from: 0, to: 3, insert: "model" },
      { from: 11, to: 14, insert: "model" },
    ]);
    Y.applyUpdate(b, Y.encodeStateAsUpdate(a));
    Y.applyUpdate(a, Y.encodeStateAsUpdate(b));
    expect(a.getText("content").toString()).toBe("model\ntyped middle\nmodel\n");
    expect(b.getText("content").toString()).toBe(a.getText("content").toString());
  });
});
