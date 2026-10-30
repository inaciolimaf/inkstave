/**
 * In-process fake of the spec-29 collab server for fast Vitest collab tests.
 * It mirrors the server's y-protocols behaviour (sync handshake + update relay)
 * without a real socket or network.
 */
import * as decoding from "lib0/decoding";
import * as encoding from "lib0/encoding";
import * as syncProtocol from "y-protocols/sync";
import * as Y from "yjs";

const MESSAGE_SYNC = 0;
const MESSAGE_AWARENESS = 1;

type Handler = ((event: unknown) => void) | null;

export interface FakeCollabServer {
  serverDoc: Y.Doc;
  WebSocketImpl: typeof WebSocket;
  /** Force-close a socket by its URL token suffix (to simulate a drop). */
  dropAll: () => void;
  socketCount: () => number;
}

export function makeFakeCollabServer(): FakeCollabServer {
  const serverDoc = new Y.Doc();
  const text = serverDoc.getText("content");
  void text;
  const sockets = new Set<FakeWebSocket>();

  class FakeWebSocket {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;

    readyState = FakeWebSocket.CONNECTING;
    binaryType = "arraybuffer";
    bufferedAmount = 0;
    onopen: Handler = null;
    onmessage: Handler = null;
    onclose: Handler = null;
    onerror: Handler = null;

    constructor(public url: string) {
      sockets.add(this);
      queueMicrotask(() => {
        if (this.readyState !== FakeWebSocket.CONNECTING) return;
        this.readyState = FakeWebSocket.OPEN;
        this.onopen?.({});
        // The server sends its Sync Step 1 on connect (like spec 29).
        const encoder = encoding.createEncoder();
        encoding.writeVarUint(encoder, MESSAGE_SYNC);
        syncProtocol.writeSyncStep1(encoder, serverDoc);
        this._deliver(encoding.toUint8Array(encoder));
      });
    }

    send(data: Uint8Array): void {
      const decoder = decoding.createDecoder(data);
      const messageType = decoding.readVarUint(decoder);
      if (messageType === MESSAGE_SYNC) {
        const encoder = encoding.createEncoder();
        encoding.writeVarUint(encoder, MESSAGE_SYNC);
        syncProtocol.readSyncMessage(decoder, encoder, serverDoc, this);
        if (encoding.length(encoder) > 1) this._deliver(encoding.toUint8Array(encoder));
      } else if (messageType === MESSAGE_AWARENESS) {
        // Relay awareness verbatim to the other room members (like spec 29).
        for (const other of sockets) {
          if (other !== this && other.readyState === FakeWebSocket.OPEN) other._deliver(data);
        }
      }
    }

    close(): void {
      if (this.readyState === FakeWebSocket.CLOSED) return;
      this.readyState = FakeWebSocket.CLOSED;
      sockets.delete(this);
      this.onclose?.({});
    }

    private _deliver(payload: Uint8Array): void {
      const copy = payload.slice();
      this.onmessage?.({
        data: copy.buffer.slice(copy.byteOffset, copy.byteOffset + copy.byteLength),
      });
    }
  }

  // Relay every server-applied update to all OTHER sockets (origin-excluded).
  serverDoc.on("update", (update: Uint8Array, origin: unknown) => {
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);
    syncProtocol.writeUpdate(encoder, update);
    const message = encoding.toUint8Array(encoder);
    for (const socket of sockets) {
      if (socket !== origin && socket.readyState === FakeWebSocket.OPEN) {
        (socket as unknown as { _deliver: (p: Uint8Array) => void })._deliver(message);
      }
    }
  });

  return {
    serverDoc,
    WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    dropAll: () => {
      for (const socket of [...sockets]) socket.close();
    },
    socketCount: () => sockets.size,
  };
}
