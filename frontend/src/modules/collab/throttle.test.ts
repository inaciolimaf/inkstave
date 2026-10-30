import { afterEach, describe, expect, it, vi } from "vitest";

import { throttle } from "./throttle";

afterEach(() => vi.useRealTimers());

describe("throttle", () => {
  it("collapses a burst into a leading + trailing call (AC8)", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const t = throttle(fn, 50);
    for (let i = 0; i < 10; i++) t(i); // rapid burst within the window
    expect(fn).toHaveBeenCalledTimes(1); // leading edge only so far
    vi.advanceTimersByTime(50);
    expect(fn).toHaveBeenCalledTimes(2); // trailing edge with the last args
    expect(fn).toHaveBeenLastCalledWith(9);
  });

  it("invokes again after the window for a fresh call", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const t = throttle(fn, 50);
    t("a");
    vi.advanceTimersByTime(60);
    t("b");
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("cancel stops a pending trailing call", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const t = throttle(fn, 50);
    t("a");
    t("b");
    t.cancel();
    vi.advanceTimersByTime(100);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
