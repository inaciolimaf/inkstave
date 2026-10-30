import { fireEvent, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useShortcuts } from "./shortcuts";

describe("useShortcuts", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it.each(["ctrlKey", "metaKey"])("fires mod+s on %s and suppresses the browser action", (modifier) => {
    const save = vi.fn();
    renderHook(() => useShortcuts({ "mod+s": save }));
    const notPrevented = fireEvent.keyDown(window, { key: "S", [modifier]: true });
    expect(save).toHaveBeenCalledOnce();
    expect(notPrevented).toBe(false);
  });

  it("fires a mod shortcut from inside a text field", () => {
    const save = vi.fn();
    renderHook(() => useShortcuts({ "mod+s": save }));
    const input = document.body.appendChild(document.createElement("input"));
    fireEvent.keyDown(input, { key: "s", ctrlKey: true });
    expect(save).toHaveBeenCalledOnce();
  });

  it("ignores a bare key while typing in a text field", () => {
    const next = vi.fn();
    renderHook(() => useShortcuts({ j: next }));
    const input = document.body.appendChild(document.createElement("input"));
    fireEvent.keyDown(input, { key: "j" });
    expect(next).not.toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "j" });
    expect(next).toHaveBeenCalledOnce();
  });

  it("listens only while active and calls the latest handler", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ handler, active }) => useShortcuts({ "mod+s": handler }, active), {
      initialProps: { handler: first, active: false },
    });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    expect(first).not.toHaveBeenCalled();
    rerender({ handler: second, active: true });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledOnce();
  });
});
