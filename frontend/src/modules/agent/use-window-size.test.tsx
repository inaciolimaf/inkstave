import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { LARGE_WIDTH, clampSize, readStoredSize, useWindowSize } from "./use-window-size";
import { WindowResizeHandles } from "./window-resize-handles";

const KEY = "inkstave:agent-window";

function Harness() {
  const resize = useWindowSize();
  return (
    <section data-testid="panel" style={{ width: resize.size?.width ?? 0 }}>
      <WindowResizeHandles resize={resize} />
    </section>
  );
}

describe("clampSize", () => {
  const viewport = { width: 1000, height: 800 };

  it("keeps the window inside the screen", () => {
    expect(clampSize({ width: 5000, height: 5000 }, viewport)).toEqual({ width: 968, height: 704 });
  });

  it("never goes below the smallest usable size", () => {
    expect(clampSize({ width: 10, height: 10 }, viewport)).toEqual({ width: 320, height: 360 });
  });
});

describe("useWindowSize", () => {
  beforeEach(() => localStorage.clear());

  it("ignores a stored value it cannot read", () => {
    localStorage.setItem(KEY, "not json");
    expect(readStoredSize()).toBeNull();
    localStorage.setItem(KEY, JSON.stringify({ width: "wide" }));
    expect(readStoredSize()).toBeNull();
  });

  it("enlarges in one action, remembers it, and returns to the default", () => {
    const { result } = renderHook(() => useWindowSize());
    expect(result.current.size).toBeNull();

    act(() => result.current.toggleLarge());
    expect(result.current.large).toBe(true);
    expect(readStoredSize()?.width).toBe(LARGE_WIDTH);

    act(() => result.current.toggleLarge());
    expect(result.current.size).toBeNull();
    expect(readStoredSize()).toBeNull();
  });

  it("grows by keyboard from the corner, towards the upper left", () => {
    render(<Harness />);
    const rect = { width: 416, height: 500 } as DOMRect;
    screen.getByTestId("panel").getBoundingClientRect = () => rect;
    fireEvent.keyDown(screen.getByRole("button", { name: "Resize the agent window" }), { key: "ArrowLeft" });
    expect(readStoredSize()).toEqual({ width: 440, height: 500 });
  });

  it("leaves other keys alone", () => {
    render(<Harness />);
    fireEvent.keyDown(screen.getByRole("button", { name: "Resize the agent window" }), { key: "Tab" });
    expect(readStoredSize()).toBeNull();
  });
});
