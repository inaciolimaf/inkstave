import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useEditorSettings } from "./use-editor-settings";

beforeEach(() => localStorage.clear());

describe("useEditorSettings", () => {
  it("starts from sensible defaults", () => {
    const { result } = renderHook(() => useEditorSettings());
    expect(result.current.settings).toEqual({
      fontSize: 14,
      keymap: "default",
      lineWrapping: true,
    });
  });

  it("persists changes and clamps the font size", () => {
    const { result } = renderHook(() => useEditorSettings());
    act(() => result.current.update({ fontSize: 99 }));
    expect(result.current.settings.fontSize).toBe(24);
    act(() => result.current.update({ lineWrapping: false }));
    const stored = JSON.parse(localStorage.getItem("inkstave:editor-settings")!);
    expect(stored).toMatchObject({ fontSize: 24, lineWrapping: false });
  });

  it("reads persisted settings on init", () => {
    localStorage.setItem(
      "inkstave:editor-settings",
      JSON.stringify({ fontSize: 18, keymap: "default", lineWrapping: false }),
    );
    const { result } = renderHook(() => useEditorSettings());
    expect(result.current.settings.fontSize).toBe(18);
    expect(result.current.settings.lineWrapping).toBe(false);
  });
});
