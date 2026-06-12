import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { VersionConflictError, saveDocument } from "../api";
import { useDocumentAutosave } from "./use-document-autosave";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, saveDocument: vi.fn() };
});

const save = saveDocument as Mock;
const LOADED = { id: "d1", content: "hello", version: 5 };

beforeEach(() => {
  vi.useFakeTimers();
  save.mockReset();
});
afterEach(() => vi.useRealTimers());

function setup() {
  return renderHook(() => useDocumentAutosave("p", LOADED));
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("useDocumentAutosave", () => {
  it("seeds clean and goes dirty → saving → clean, advancing the version", async () => {
    save.mockResolvedValue({ version: 6 });
    const { result } = setup();
    expect(result.current.status).toBe("clean");

    act(() => result.current.onLocalChange("hello world"));
    expect(result.current.status).toBe("dirty");
    expect(result.current.hasUnsaved).toBe(true);

    await advance(1000);
    expect(save).toHaveBeenCalledWith("p", "d1", "hello world", 5);
    expect(result.current.status).toBe("clean");

    // Next save uses the advanced version.
    act(() => result.current.onLocalChange("again"));
    await advance(1000);
    expect(save).toHaveBeenLastCalledWith("p", "d1", "again", 6);
  });

  it("does not save when the text is unchanged", async () => {
    const { result } = setup();
    act(() => result.current.onLocalChange("hello")); // equals server text
    expect(result.current.status).toBe("clean");
    await advance(3000);
    expect(save).not.toHaveBeenCalled();
  });

  it("debounces rapid edits into a single save", async () => {
    save.mockResolvedValue({ version: 6 });
    const { result } = setup();
    act(() => result.current.onLocalChange("a"));
    await advance(500);
    act(() => result.current.onLocalChange("ab"));
    await advance(500);
    act(() => result.current.onLocalChange("abc"));
    expect(save).not.toHaveBeenCalled(); // still within the debounce window
    await advance(1000);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("p", "d1", "abc", 5);
  });

  it("coalesces edits made during an in-flight save (single-flight)", async () => {
    let release!: () => void;
    save.mockImplementationOnce(
      () => new Promise<{ version: number }>((res) => (release = () => res({ version: 6 }))),
    );
    save.mockResolvedValue({ version: 7 });
    const { result } = setup();

    act(() => result.current.onLocalChange("a"));
    await advance(1000);
    expect(result.current.status).toBe("saving");

    act(() => result.current.onLocalChange("ab")); // typed during the save
    await act(async () => {
      release();
      await Promise.resolve();
    });
    await advance(0);

    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenNthCalledWith(1, "p", "d1", "a", 5);
    expect(save).toHaveBeenLastCalledWith("p", "d1", "ab", 6);
    expect(result.current.status).toBe("clean");
  });

  it("enters conflict on 409 and resolves via reload or keep-mine", async () => {
    save.mockRejectedValueOnce(
      new VersionConflictError({ currentVersion: 9, currentContent: "server text" }),
    );
    const { result } = setup();
    act(() => result.current.onLocalChange("mine"));
    await advance(1000);
    expect(result.current.status).toBe("conflict");
    expect(result.current.conflict).toEqual({ currentVersion: 9, currentContent: "server text" });

    act(() => result.current.resolveReload());
    expect(result.current.status).toBe("clean");
    expect(result.current.displayText).toBe("server text");
    expect(result.current.conflict).toBeNull();
  });

  it("keep-mine re-saves the local text against the new server version", async () => {
    save.mockRejectedValueOnce(
      new VersionConflictError({ currentVersion: 9, currentContent: "srv" }),
    );
    save.mockResolvedValue({ version: 10 });
    const { result } = setup();
    act(() => result.current.onLocalChange("mine"));
    await advance(1000);
    expect(result.current.status).toBe("conflict");

    act(() => result.current.resolveKeepMine());
    await advance(0);
    expect(save).toHaveBeenLastCalledWith("p", "d1", "mine", 9);
    expect(result.current.status).toBe("clean");
  });

  it("retries with backoff on transient failure, then succeeds", async () => {
    save.mockRejectedValueOnce(new Error("network")).mockResolvedValue({ version: 6 });
    const { result } = setup();
    act(() => result.current.onLocalChange("a"));
    await advance(1000);
    expect(result.current.status).toBe("error");

    await advance(1000); // first backoff
    expect(save).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe("clean");
  });

  it("stops auto-retrying after the cap (no busy loop)", async () => {
    save.mockRejectedValue(new Error("down"));
    const { result } = setup();
    act(() => result.current.onLocalChange("a"));
    await advance(1000); // attempt 1 -> error, schedule
    await advance(1000); // retry 2
    await advance(2000); // retry 3
    await advance(4000); // retry 4
    await advance(8000); // retry 5 -> exceeds cap, stop
    const callsAtCap = save.mock.calls.length;
    await advance(60_000); // no further auto-retries
    expect(save.mock.calls.length).toBe(callsAtCap);
    expect(result.current.status).toBe("error");

    // Manual retry still works.
    save.mockResolvedValueOnce({ version: 6 });
    await act(async () => {
      result.current.saveNow();
      await Promise.resolve();
    });
    expect(result.current.status).toBe("clean");
  });

  it("flushes when the tab becomes hidden", async () => {
    save.mockResolvedValue({ version: 6 });
    const { result } = setup();
    act(() => result.current.onLocalChange("edited"));
    expect(result.current.status).toBe("dirty");

    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      await Promise.resolve();
    });
    expect(save).toHaveBeenCalledWith("p", "d1", "edited", 5);
    expect(result.current.status).toBe("clean");
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  });

  it("flushes on the window 'online' event", async () => {
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    save.mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ version: 6 });
    const { result } = setup();
    act(() => result.current.onLocalChange("a"));
    await advance(1000);
    expect(result.current.status).toBe("offline");

    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
    await act(async () => {
      window.dispatchEvent(new Event("online"));
      await Promise.resolve();
    });
    expect(result.current.status).toBe("clean");
  });
});
