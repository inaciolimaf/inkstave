/** How large the agent's conversation reads: stepped by the reader, remembered on this browser. */
import { useCallback, useState } from "react";

const KEY = "inkstave:agent-text-scale";
/** Multipliers of the type scale. The default is a step above the rest of the app: a reply is read at length. */
export const TEXT_SCALES = [0.9, 1, 1.15, 1.3, 1.5, 1.75] as const;
export const DEFAULT_TEXT_SCALE = 1.15;

export function readStoredScale(): number {
  try {
    const stored = Number(localStorage.getItem(KEY));
    return (TEXT_SCALES as readonly number[]).includes(stored) ? stored : DEFAULT_TEXT_SCALE;
  } catch {
    return DEFAULT_TEXT_SCALE;
  }
}

function storeScale(scale: number) {
  try {
    if (scale === DEFAULT_TEXT_SCALE) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, String(scale));
  } catch {
    // A convenience: without storage the choice lasts until the page closes.
  }
}

export function useTextScale() {
  const [scale, setScale] = useState(readStoredScale);
  const index = (TEXT_SCALES as readonly number[]).indexOf(scale);

  const step = useCallback(
    (by: number) => {
      const next = TEXT_SCALES[Math.min(TEXT_SCALES.length - 1, Math.max(0, index + by))]!;
      setScale(next);
      storeScale(next);
    },
    [index],
  );

  return {
    scale,
    canGrow: index < TEXT_SCALES.length - 1,
    canShrink: index > 0,
    grow: useCallback(() => step(1), [step]),
    shrink: useCallback(() => step(-1), [step]),
  };
}

export type TextScale = ReturnType<typeof useTextScale>;
