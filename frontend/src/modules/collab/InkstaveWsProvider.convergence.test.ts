import { describe, expect, it, vi } from "vitest";
import * as Y from "yjs";

import { makeFakeCollabServer } from "./collab-test-utils";
import { makeClient, syncedOnce, tick } from "./InkstaveWsProvider.test-helpers";

describe("InkstaveWsProvider convergence", () => {
  it("two clients converge with no echo (AC2/AC5)", async () => {
    const server = makeFakeCollabServer();
    const a = makeClient(server);
    const b = makeClient(server);
    await Promise.all([syncedOnce(a.provider), syncedOnce(b.provider)]);

    a.text.insert(0, "hello");
    await tick();

    expect(b.text.toString()).toBe("hello"); // propagated to B
    expect(a.text.toString()).toBe("hello"); // not echoed back / doubled on A
    expect(server.serverDoc.getText("content").toString()).toBe("hello");

    a.provider.destroy();
    b.provider.destroy();
  });

  it("flush resolves and the server holds the latest text (AC8)", async () => {
    const server = makeFakeCollabServer();
    const a = makeClient(server);
    await syncedOnce(a.provider);

    a.text.insert(0, "compile me");
    await a.provider.flush();

    expect(server.serverDoc.getText("content").toString()).toBe("compile me");
    a.provider.destroy();
  });

  it("two live clients converge on a concurrent insert at the same position (AC2)", async () => {
    const server = makeFakeCollabServer();
    const a = makeClient(server, "d1");
    const b = makeClient(server, "d1");
    await Promise.all([syncedOnce(a.provider), syncedOnce(b.provider)]);

    // Both clients insert at the SAME position within the same tick, while both
    // are live. The CRDT must reconcile to one deterministic, identical result.
    a.text.insert(0, "AAA");
    b.text.insert(0, "BBB");
    await tick();
    await tick(); // let the relayed updates settle on both peers

    const serverText = server.serverDoc.getText("content").toString();
    expect(a.text.toString()).toBe(b.text.toString()); // CRDT convergence
    expect(a.text.toString()).toBe(serverText); // and they match the server
    // The merged text contains both inserts exactly once (no loss, no dup).
    expect(serverText).toContain("AAA");
    expect(serverText).toContain("BBB");
    expect(serverText.length).toBe(6);

    a.provider.destroy();
    b.provider.destroy();
  });

  it("merges offline edits with concurrent server edits on reconnect (AC4)", async () => {
    // Deterministic, no real wall-clock: fake timers + a seeded jitter so the
    // backoff delay is exact and we advance precisely past it.
    vi.useFakeTimers();
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(0.5);
    try {
      const server = makeFakeCollabServer();
      const a = makeClient(server);
      await vi.advanceTimersByTimeAsync(0); // getToken + queued connect
      await syncedOnce(a.provider);

      server.dropAll(); // A goes offline
      a.text.insert(0, "offline-"); // edited while disconnected (stays local)
      server.serverDoc.getText("content").insert(0, "server-"); // concurrent server edit

      // Backoff for the first attempt is `random() * 500` = 250 ms with the seed.
      // Advance just past it, then drain the resync handshake microtasks.
      await vi.advanceTimersByTimeAsync(300);
      await vi.advanceTimersByTimeAsync(0);

      const merged = a.text.toString();
      expect(merged).toContain("offline-");
      expect(merged).toContain("server-"); // no lost characters, no duplication
      expect(server.serverDoc.getText("content").toString()).toContain("offline-");
      a.provider.destroy();
    } finally {
      randomSpy.mockRestore();
      vi.useRealTimers();
    }
  });
});

// --- undo scoping: local-only revert, remote edits preserved (AC9 / spec 31) - #

describe("InkstaveWsProvider undo scoping", () => {
  it("undo reverts only the local change group, leaving the remote edit intact", async () => {
    const server = makeFakeCollabServer();
    const a = makeClient(server, "d1");
    const b = makeClient(server, "d1");
    await Promise.all([syncedOnce(a.provider), syncedOnce(b.provider)]);

    // Wire the local undo manager exactly as `useCollabDoc.ts` does: a
    // `Y.UndoManager` over the local text. It tracks the default (`null`) origin
    // — i.e. local edits — and ignores remote updates (origin = the provider).
    const undoManager = new Y.UndoManager(a.text);

    // 1. Local user types a change group (default/null origin → tracked).
    a.text.insert(0, "local");
    await tick();

    // 2. A concurrent remote edit propagates in from B (origin = provider).
    b.text.insert(b.text.length, "-remote");
    await tick();

    const beforeUndo = a.text.toString();
    expect(beforeUndo).toContain("local");
    expect(beforeUndo).toContain("-remote");

    // 3. Undo the local change group only.
    undoManager.undo();
    await tick();

    // 4. Only the local insert is reverted; the remote edit remains.
    const afterUndo = a.text.toString();
    expect(afterUndo).not.toContain("local");
    expect(afterUndo).toContain("-remote");
    expect(afterUndo).toBe("-remote");

    undoManager.destroy();
    a.provider.destroy();
    b.provider.destroy();
  });
});
