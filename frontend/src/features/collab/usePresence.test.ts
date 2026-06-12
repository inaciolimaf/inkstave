import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Awareness, applyAwarenessUpdate, encodeAwarenessUpdate } from "y-protocols/awareness";
import * as Y from "yjs";

import { colorForUser } from "./colors";
import type { CollabDocSession } from "./useCollabDoc";
import { usePresence } from "./usePresence";

function fakeSession() {
  const ydoc = new Y.Doc();
  return { awareness: new Awareness(ydoc) } as unknown as CollabDocSession;
}

afterEach(() => vi.useRealTimers());

describe("usePresence", () => {
  it("publishes the local user identity once with a deterministic color", () => {
    const session = fakeSession();
    renderHook(() => usePresence(session, { id: "u1", name: "Alice" }));
    expect(session.awareness.getLocalState()?.user).toMatchObject({
      id: "u1",
      name: "Alice",
      color: colorForUser("u1"),
    });
  });

  it("marks idle after the threshold and clears on activity (AC6)", async () => {
    vi.useFakeTimers();
    const session = fakeSession();
    const { result } = renderHook(() =>
      usePresence(session, { id: "u1", name: "A" }, { idleAfterMs: 100 }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(150);
    });
    expect(session.awareness.getLocalState()?.idle).toBe(true);
    await act(async () => {
      result.current.markActivity();
    });
    expect(session.awareness.getLocalState()?.idle).toBe(false);
  });

  it("lists present users deduplicated, including a remote peer (AC4)", () => {
    const session = fakeSession();
    const { result } = renderHook(() => usePresence(session, { id: "me", name: "Me" }));

    const peer = new Awareness(new Y.Doc());
    peer.setLocalStateField("user", { id: "a", name: "Alice", color: "#ff0000" });
    act(() => {
      applyAwarenessUpdate(
        session.awareness,
        encodeAwarenessUpdate(peer, [peer.clientID]),
        "remote",
      );
    });

    const ids = result.current.users.map((u) => u.id).sort();
    expect(ids).toEqual(["a", "me"]);
    expect(result.current.users.find((u) => u.id === "me")?.isLocal).toBe(true);
    expect(result.current.users.find((u) => u.id === "a")?.color).toBe("#ff0000");
  });
});
