/**
 * `flush()` resolves when the server has applied the local edits sent before it (spec 31 AC8). The reply to
 * the SyncStep1 that flush sends is the ack, so these tests drive the socket by hand.
 */
import * as encoding from "lib0/encoding";
import { afterEach, describe, expect, it } from "vitest";
import * as syncProtocol from "y-protocols/sync";
import * as Y from "yjs";

import { ControllableWS, makeBareProvider, tick } from "./InkstaveWsProvider.test-helpers";

const MESSAGE_SYNC = 0;

/** A SyncStep2 frame carrying everything in `serverDoc`, as the server sends in reply to a SyncStep1. */
function step2Frame(serverDoc: Y.Doc): ArrayBuffer {
  const encoder = encoding.createEncoder();
  encoding.writeVarUint(encoder, MESSAGE_SYNC);
  syncProtocol.writeSyncStep2(encoder, serverDoc);
  const bytes = encoding.toUint8Array(encoder);
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

async function openSocket() {
  const made = makeBareProvider();
  await tick();
  const socket = ControllableWS.instances[ControllableWS.instances.length - 1];
  socket.open();
  return { ...made, socket };
}

let cleanup: (() => void) | null = null;
afterEach(() => {
  cleanup?.();
  cleanup = null;
  ControllableWS.instances.length = 0;
});

describe("InkstaveWsProvider.flush", () => {
  it("waits for the server's reply to a SyncStep1 sent after the edits", async () => {
    const { ydoc, provider, socket } = await openSocket();
    cleanup = () => provider.destroy();
    let resolved = false;
    ydoc.getText("content").insert(0, "unsaved");

    const done = provider.flush().then(() => {
      resolved = true;
    });
    await tick();
    expect(resolved).toBe(false);

    // Replies come in order: the handshake's first, then the one to the flush's SyncStep1.
    socket.onmessage?.({ data: step2Frame(new Y.Doc()) });
    await tick();
    expect(resolved).toBe(false);
    socket.onmessage?.({ data: step2Frame(new Y.Doc()) });
    await done;
    expect(resolved).toBe(true);
  });

  it("does not take the reply to an earlier SyncStep1 as its ack", async () => {
    const { provider, socket } = await openSocket();
    cleanup = () => provider.destroy();
    // open() sent the handshake SyncStep1; its reply is not an ack for the flush's own SyncStep1.
    let resolved = false;
    void provider.flush().then(() => {
      resolved = true;
    });
    socket.onmessage?.({ data: step2Frame(new Y.Doc()) });
    await tick();
    expect(resolved).toBe(false);
    socket.onmessage?.({ data: step2Frame(new Y.Doc()) });
    await tick();
    expect(resolved).toBe(true);
  });

  it("resolves at once when no socket is open", async () => {
    const { provider } = makeBareProvider();
    cleanup = () => provider.destroy();
    await expect(provider.flush()).resolves.toBeUndefined();
  });

  it("resolves when the socket closes before the server replies", async () => {
    const { provider, socket } = await openSocket();
    cleanup = () => provider.destroy();
    const done = provider.flush();
    socket.fail(1006);
    await expect(done).resolves.toBeUndefined();
  });
});
