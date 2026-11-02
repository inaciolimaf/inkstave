/** The agent window's size on a wide screen: dragged, stepped by keyboard, and remembered. */
import { type KeyboardEvent, type PointerEvent, useCallback, useRef, useState } from "react";

export interface WindowSize {
  width: number;
  height: number;
}

export type DragEdge = "top" | "left" | "corner";

const KEY = "inkstave:agent-window";
const MIN_WIDTH = 320;
const MIN_HEIGHT = 360;
export const LARGE_WIDTH = 640;
const KEY_STEP = 24;
// Room the window leaves around itself: it sits 16 px from the edges, under the editor's bar.
const MARGIN_X = 32;
const MARGIN_Y = 96;

/** A size that fits this viewport; the minimum wins on a screen too small for it. */
export function clampSize(size: WindowSize, viewport: WindowSize): WindowSize {
  return {
    width: Math.max(MIN_WIDTH, Math.min(size.width, viewport.width - MARGIN_X)),
    height: Math.max(MIN_HEIGHT, Math.min(size.height, viewport.height - MARGIN_Y)),
  };
}

function viewport(): WindowSize {
  return { width: window.innerWidth, height: window.innerHeight };
}

export function readStoredSize(): WindowSize | null {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? "null");
    const { width, height } = (parsed ?? {}) as Partial<WindowSize>;
    return typeof width === "number" && typeof height === "number" ? { width, height } : null;
  } catch {
    return null;
  }
}

function storeSize(size: WindowSize | null) {
  try {
    if (size) localStorage.setItem(KEY, JSON.stringify(size));
    else localStorage.removeItem(KEY);
  } catch {
    // Remembering the size is a convenience: without storage it lasts until the page closes.
  }
}

const KEY_STEPS: Record<string, Partial<WindowSize>> = {
  ArrowLeft: { width: KEY_STEP },
  ArrowRight: { width: -KEY_STEP },
  ArrowUp: { height: KEY_STEP },
  ArrowDown: { height: -KEY_STEP },
};

/** The window is pinned to the lower right, so it grows towards the upper left. */
export function useWindowSize() {
  const [size, setSize] = useState(readStoredSize);
  const latest = useRef(size);

  const apply = useCallback((next: WindowSize | null, persist: boolean) => {
    latest.current = next;
    setSize(next);
    if (persist) storeSize(next);
  }, []);

  const startDrag = useCallback(
    (edge: DragEdge, event: PointerEvent<HTMLElement>) => {
      const panel = event.currentTarget.closest("section");
      if (!panel) return;
      event.preventDefault();
      const handle = event.currentTarget;
      const start = panel.getBoundingClientRect();
      const { clientX, clientY, pointerId } = event;
      handle.setPointerCapture(pointerId);
      const move = (e: globalThis.PointerEvent) => {
        const width = edge === "top" ? start.width : start.width + clientX - e.clientX;
        const height = edge === "left" ? start.height : start.height + clientY - e.clientY;
        apply(clampSize({ width, height }, viewport()), false);
      };
      const stop = () => {
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", stop);
        handle.removeEventListener("pointercancel", stop);
        storeSize(latest.current);
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", stop);
      handle.addEventListener("pointercancel", stop);
    },
    [apply],
  );

  const onResizeKey = useCallback(
    (event: KeyboardEvent<HTMLElement>) => {
      const step = KEY_STEPS[event.key];
      const panel = event.currentTarget.closest("section");
      if (!step || !panel) return;
      event.preventDefault();
      const { width, height } = panel.getBoundingClientRect();
      const next = { width: width + (step.width ?? 0), height: height + (step.height ?? 0) };
      apply(clampSize(next, viewport()), true);
    },
    [apply],
  );

  const large = size !== null && size.width >= LARGE_WIDTH;
  const toggleLarge = useCallback(() => {
    const wanted = { width: LARGE_WIDTH, height: window.innerHeight };
    apply(large ? null : clampSize(wanted, viewport()), true);
  }, [apply, large]);

  return { size, large, startDrag, onResizeKey, toggleLarge };
}
