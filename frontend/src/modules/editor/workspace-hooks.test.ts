/** The flush before a compile or an agent turn: it waits for the open session, and never for longer than the deadline. */
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FLUSH_DEADLINE_MS, flushWithDeadline, useFlushBeforeCompile } from "./workspace-hooks";

afterEach(() => {
  vi.useRealTimers();
});

function deferred() {
  let resolve: () => void = () => undefined;
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("useFlushBeforeCompile", () => {
  it("waits for the flush that the open session registered", async () => {
    const { result } = renderHook(() => useFlushBeforeCompile());
    const gate = deferred();
    const flush = vi.fn(() => gate.promise);
    act(() => result.current.registerFlush(flush));

    let done = false;
    const sent = result.current.flushBeforeCompile().then(() => {
      done = true;
    });
    await act(() => Promise.resolve());
    expect(flush).toHaveBeenCalledTimes(1);
    expect(done).toBe(false);

    gate.resolve();
    await sent;
    expect(done).toBe(true);
  });

  it("resolves at once when no session is open", async () => {
    const { result } = renderHook(() => useFlushBeforeCompile());
    await expect(result.current.flushBeforeCompile()).resolves.toBeUndefined();
  });

  it("stops waiting after the deadline when the flush never resolves", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useFlushBeforeCompile());
    act(() => result.current.registerFlush(() => new Promise<void>(() => undefined)));

    let done = false;
    const sent = result.current.flushBeforeCompile().then(() => {
      done = true;
    });
    await act(() => vi.advanceTimersByTimeAsync(FLUSH_DEADLINE_MS - 1));
    expect(done).toBe(false);
    await act(() => vi.advanceTimersByTimeAsync(1));
    await sent;
    expect(done).toBe(true);
  });

  it("the send goes on when the flush rejects", async () => {
    const { result } = renderHook(() => useFlushBeforeCompile());
    act(() => result.current.registerFlush(() => Promise.reject(new Error("offline"))));
    await expect(result.current.flushBeforeCompile()).resolves.toBeUndefined();
  });

  it("a session that unregisters stops being waited for", async () => {
    const { result } = renderHook(() => useFlushBeforeCompile());
    const flush = vi.fn(() => Promise.resolve());
    act(() => result.current.registerFlush(flush));
    act(() => result.current.registerFlush(null));
    await result.current.flushBeforeCompile();
    expect(flush).not.toHaveBeenCalled();
  });
});

describe("flushWithDeadline", () => {
  it("returns the flush's own result when it finishes in time", async () => {
    vi.useFakeTimers();
    const done = vi.fn(() => Promise.resolve());
    await expect(flushWithDeadline(done, 100)).resolves.toBeUndefined();
    expect(done).toHaveBeenCalledTimes(1);
  });
});
