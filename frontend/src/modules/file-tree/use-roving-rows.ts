import { useCallback, useEffect, useRef, useState } from "react";

import type { FlatNode } from "./types";

/** Roving tabindex over the visible rows: which one holds focus, and how to move it. */
export function useRovingRows(flat: FlatNode[]) {
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const rowRefs = useRef(new Map<string, HTMLElement>());

  // Seed roving focus on the first visible node once the tree loads.
  useEffect(() => {
    if (!focusedId && flat.length > 0) setFocusedId(flat[0].node.id);
  }, [flat, focusedId]);

  const focusRow = useCallback((id: string) => {
    setFocusedId(id);
    rowRefs.current.get(id)?.focus();
  }, []);

  const registerRow = useCallback((id: string, el: HTMLElement | null) => {
    if (el) rowRefs.current.set(id, el);
    else rowRefs.current.delete(id);
  }, []);

  return { focusedId, focusRow, registerRow };
}
