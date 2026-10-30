import { renderHook, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCollabDoc } from "./useCollabDoc";

class FakeWS {
  static created = 0;
  static closed = 0;
  readyState = 0;
  binaryType = "arraybuffer";
  bufferedAmount = 0;
  onopen: unknown = null;
  onmessage: unknown = null;
  onclose: unknown = null;
  onerror: unknown = null;
  constructor() {
    FakeWS.created += 1;
  }
  send(): void {}
  close(): void {
    FakeWS.closed += 1;
    this.readyState = 3;
  }
}

beforeEach(() => {
  FakeWS.created = 0;
  FakeWS.closed = 0;
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
});
afterEach(() => vi.unstubAllGlobals());

const opts = { projectId: "p1", documentId: "d1", getToken: () => "tok" };

describe("useCollabDoc", () => {
  it("creates one session and destroys the provider on unmount", async () => {
    const { result, unmount } = renderHook(() => useCollabDoc(opts));
    await waitFor(() => expect(result.current).not.toBeNull());
    expect(result.current!.text.constructor.name).toBe("YText");
    expect(result.current!.cmExtension).toBeDefined();
    expect(FakeWS.created).toBe(1);

    unmount();
    expect(FakeWS.closed).toBe(1); // provider.destroy() closed the socket
  });

  it("returns null when disabled", () => {
    const { result } = renderHook(() => useCollabDoc({ ...opts, enabled: false }));
    expect(result.current).toBeNull();
    expect(FakeWS.created).toBe(0);
  });

  it("returns null without a documentId", () => {
    const { result } = renderHook(() => useCollabDoc({ ...opts, documentId: null }));
    expect(result.current).toBeNull();
  });

  it("is idempotent under StrictMode double-mount (one live session, clean teardown)", async () => {
    const { result, unmount } = renderHook(() => useCollabDoc(opts), { wrapper: StrictMode });
    await waitFor(() => expect(result.current).not.toBeNull());
    // The first provider is torn down before its async connect opens a socket, so
    // only the surviving provider holds a live socket.
    expect(FakeWS.created).toBe(1);
    unmount();
    expect(FakeWS.closed).toBe(FakeWS.created); // every opened socket is closed (no leak)
  });

  it("recreates the session when the documentId changes", async () => {
    const { result, rerender } = renderHook(
      (p: { documentId: string }) => useCollabDoc({ ...opts, documentId: p.documentId }),
      { initialProps: { documentId: "d1" } },
    );
    await waitFor(() => expect(result.current).not.toBeNull());
    const firstDoc = result.current!.ydoc;
    rerender({ documentId: "d2" });
    await waitFor(() => expect(result.current!.ydoc).not.toBe(firstDoc));
    expect(FakeWS.closed).toBe(1); // the previous session was torn down
  });

  it("gives each document a fresh awareness — no presence bleed across docs (spec 35 AC4)", async () => {
    const { result, rerender } = renderHook(
      (p: { documentId: string }) => useCollabDoc({ ...opts, documentId: p.documentId }),
      { initialProps: { documentId: "d1" } },
    );
    await waitFor(() => expect(result.current).not.toBeNull());
    const awarenessA = result.current!.awareness;
    awarenessA.setLocalStateField("user", { id: "u1", name: "Doc-A user" });
    expect(awarenessA.getStates().size).toBeGreaterThan(0);

    rerender({ documentId: "d2" });
    await waitFor(() => expect(result.current!.awareness).not.toBe(awarenessA));
    const awarenessB = result.current!.awareness;
    // Doc B starts with no states from doc A (separate Y.Doc + Awareness).
    const bleed = [...awarenessB.getStates().values()].some(
      (s) => (s as { user?: { name?: string } }).user?.name === "Doc-A user",
    );
    expect(bleed).toBe(false);
    expect(awarenessB.clientID).not.toBe(awarenessA.clientID);
  });
});
