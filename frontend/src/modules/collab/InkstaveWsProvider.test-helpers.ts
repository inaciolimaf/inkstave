/**
 * Shared setup for the InkstaveWsProvider test suites: live fake-server clients
 * plus a hand-controllable fake socket for the state-machine / backoff tests.
 * Kept in a sibling (non-test) module so each split test file imports the same
 * fixtures instead of re-declaring them.
 */
import { Awareness } from "y-protocols/awareness";
import * as Y from "yjs";

import { InkstaveWsProvider } from "./InkstaveWsProvider";
import { makeFakeCollabServer } from "./collab-test-utils";

/** A live client wired to the in-process fake collab server. */
export function makeClient(server: ReturnType<typeof makeFakeCollabServer>, id = "d1") {
  const ydoc = new Y.Doc();
  const awareness = new Awareness(ydoc);
  const provider = new InkstaveWsProvider({
    url: "ws://test/doc",
    documentId: id,
    ydoc,
    awareness,
    getToken: () => "jwt-token",
    WebSocketImpl: server.WebSocketImpl,
  });
  return { ydoc, awareness, provider, text: ydoc.getText("content") };
}

export function syncedOnce(provider: InkstaveWsProvider): Promise<void> {
  if (provider.synced) return Promise.resolve();
  return new Promise((resolve) => provider.once("synced", () => resolve()));
}

export const tick = () => new Promise((r) => setTimeout(r, 0));

// --- a hand-controllable fake socket for state-machine / backoff / teardown - #

export class ControllableWS {
  static instances: ControllableWS[] = [];
  static readonly OPEN = 1;
  readyState = 0;
  binaryType = "arraybuffer";
  bufferedAmount = 0;
  onopen: ((e: unknown) => void) | null = null;
  onmessage: ((e: { data: ArrayBuffer }) => void) | null = null;
  onclose: ((e: unknown) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  sent: Uint8Array[] = [];
  constructor(public url: string) {
    ControllableWS.instances.push(this);
  }
  send(data: Uint8Array): void {
    this.sent.push(data);
  }
  close(): void {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.({});
  }
  open(): void {
    this.readyState = ControllableWS.OPEN;
    this.onopen?.({});
  }
  fail(code?: number): void {
    this.readyState = 3;
    this.onclose?.(code === undefined ? {} : { code });
  }
}

export function makeBareProvider() {
  const ydoc = new Y.Doc();
  const provider = new InkstaveWsProvider({
    url: "ws://test/doc",
    documentId: "d1",
    ydoc,
    awareness: new Awareness(ydoc),
    getToken: () => "tok",
    WebSocketImpl: ControllableWS as unknown as typeof WebSocket,
  });
  return { ydoc, provider };
}

export const AWARENESS_FRAME = 1; // MESSAGE_AWARENESS message-type byte

export function makeAwarenessProvider(awarenessThrottleMs: number) {
  const ydoc = new Y.Doc();
  const awareness = new Awareness(ydoc);
  const provider = new InkstaveWsProvider({
    url: "ws://test/doc",
    documentId: "d1",
    ydoc,
    awareness,
    getToken: () => "tok",
    WebSocketImpl: ControllableWS as unknown as typeof WebSocket,
    awarenessThrottleMs,
  });
  return { ydoc, awareness, provider };
}
