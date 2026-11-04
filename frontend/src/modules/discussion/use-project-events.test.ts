import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FakeEventSource, installFakeEventSource, latestEventSource } from "@/test/fake-event-source";

import { subscribeProjectEvents, useProjectEvents } from "./use-project-events";

const PROJECT = "p1";
const cleanups: Array<() => void> = [];

function subscribe(handlers: Parameters<typeof subscribeProjectEvents>[1]) {
  const unsubscribe = subscribeProjectEvents(PROJECT, handlers);
  cleanups.push(unsubscribe);
  return unsubscribe;
}

beforeEach(() => {
  installFakeEventSource();
});

afterEach(() => {
  for (const cleanup of cleanups.splice(0)) cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("subscribeProjectEvents", () => {
  it("shares one EventSource between subscribers and closes it with the last one", () => {
    const first = vi.fn();
    const second = vi.fn();
    const leaveFirst = subscribe({ onEvent: first });
    const leaveSecond = subscribe({ onEvent: second });

    expect(FakeEventSource.instances).toHaveLength(1);
    const source = latestEventSource();
    expect(source.url).toContain(`/api/v1/projects/${PROJECT}/events`);

    source.emit("chat.message_created", { id: 1, type: "chat.message_created", payload: { id: "m" } });
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);

    leaveFirst();
    expect(source.closed).toBe(false);
    leaveSecond();
    expect(source.closed).toBe(true);
  });

  it("delivers what the stream sends, and ignores frames that are not JSON", () => {
    const onEvent = vi.fn();
    subscribe({ onEvent });
    const source = latestEventSource();
    source.emit("chat.message_deleted", { id: 2, type: "chat.message_deleted", payload: { id: "m" } });
    expect(onEvent).toHaveBeenCalledWith({ id: 2, type: "chat.message_deleted", payload: { id: "m" } });

    source.emitRaw("chat.message_created", "not json");
    expect(onEvent).toHaveBeenCalledTimes(1);
  });

  it("reconnects after a drop with backoff, and tells subscribers when a connection opens", () => {
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    const onOpen = vi.fn();
    subscribe({ onOpen });

    latestEventSource().open();
    expect(onOpen).toHaveBeenCalledTimes(1);

    latestEventSource().fail();
    expect(FakeEventSource.instances).toHaveLength(1);
    // The first retry waits at most the base delay: 0.5 * 500 ms.
    vi.advanceTimersByTime(250);
    expect(FakeEventSource.instances).toHaveLength(2);

    latestEventSource().fail();
    // The second wait's ceiling doubles: 0.5 * 1000 ms.
    vi.advanceTimersByTime(499);
    expect(FakeEventSource.instances).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(FakeEventSource.instances).toHaveLength(3);

    latestEventSource().open();
    expect(onOpen).toHaveBeenCalledTimes(2);
  });

  it("caps the reconnect delay at 15 seconds", () => {
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0.999);
    subscribe({ onOpen: () => undefined });
    for (let i = 0; i < 12; i += 1) {
      latestEventSource().fail();
      vi.advanceTimersByTime(15_000);
    }
    expect(FakeEventSource.instances.length).toBeGreaterThan(10);
  });

  it("stops reconnecting once the last subscriber has left", () => {
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    const leave = subscribe({ onEvent: () => undefined });
    latestEventSource().fail();
    leave();
    vi.advanceTimersByTime(60_000);
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});

describe("useProjectEvents", () => {
  it("subscribes for the life of the component", () => {
    const { unmount } = renderHook(() => useProjectEvents(PROJECT, { onEvent: () => undefined }));
    const source = latestEventSource();
    expect(source.closed).toBe(false);
    unmount();
    expect(source.closed).toBe(true);
  });

  it("does not open a stream without a project", () => {
    renderHook(() => useProjectEvents(undefined, { onEvent: () => undefined }));
    expect(FakeEventSource.instances).toHaveLength(0);
  });
});
