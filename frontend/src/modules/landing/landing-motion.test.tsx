import { act, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentDemo } from "./agent-demo";

function stubReducedMotion(matches: boolean) {
  vi.stubGlobal("matchMedia", () => ({ matches }));
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("AgentDemo", () => {
  it("rests on the applied state without a timer under reduced motion", () => {
    stubReducedMotion(true);
    vi.useFakeTimers();

    const { container } = render(<AgentDemo />);

    expect(vi.getTimerCount()).toBe(0);
    expect(container.querySelector("figure")).toHaveTextContent("We present a concise overview");
  });

  it("plays the scripted cycle otherwise", () => {
    stubReducedMotion(false);
    vi.useFakeTimers();

    const { container } = render(<AgentDemo />);
    act(() => void vi.advanceTimersByTime(100));

    expect(vi.getTimerCount()).toBeGreaterThan(0);
    expect(container.querySelector("figure")).toHaveTextContent("comprehensive and exhaustive");
  });
});
