import { afterEach, describe, expect, it, vi } from "vitest";
import { Awareness } from "y-protocols/awareness";
import * as Y from "yjs";

import { InkstaveWsProvider } from "./InkstaveWsProvider";
import { makeFakeCollabServer } from "./collab-test-utils";
import { collectPresence } from "./usePresence";

function makeClient(server: ReturnType<typeof makeFakeCollabServer>) {
  const ydoc = new Y.Doc();
  const awareness = new Awareness(ydoc);
  const provider = new InkstaveWsProvider({
    url: "ws://test/doc",
    documentId: "d1",
    ydoc,
    awareness,
    getToken: () => "tok",
    WebSocketImpl: server.WebSocketImpl,
  });
  return { ydoc, awareness, provider };
}

const tick = () => new Promise((r) => setTimeout(r, 0));

afterEach(() => vi.useRealTimers());

describe("presence convergence (two clients via fake relay)", () => {
  it("A's user presence propagates to B with its published color (AC1-3)", async () => {
    const server = makeFakeCollabServer();
    const a = makeClient(server);
    const b = makeClient(server);
    await tick();

    a.awareness.setLocalStateField("user", { id: "ua", name: "Alice", color: "#ff0000" });
    await tick();

    const alice = collectPresence(b.awareness).find((u) => u.id === "ua");
    expect(alice).toBeDefined();
    expect(alice?.name).toBe("Alice");
    expect(alice?.color).toBe("#ff0000");

    a.provider.destroy();
    b.provider.destroy();
  });

  it("clears a disconnected peer's presence — no ghost cursors (AC7)", async () => {
    const server = makeFakeCollabServer();
    const a = makeClient(server);
    const b = makeClient(server);
    await tick();

    a.awareness.setLocalStateField("user", { id: "ua", name: "Alice", color: "#f00" });
    await tick();
    expect(collectPresence(b.awareness).some((u) => u.id === "ua")).toBe(true);

    a.provider.destroy(); // clean leave broadcasts the awareness removal
    await tick();
    expect(collectPresence(b.awareness).some((u) => u.id === "ua")).toBe(false);

    b.provider.destroy();
  });
});
