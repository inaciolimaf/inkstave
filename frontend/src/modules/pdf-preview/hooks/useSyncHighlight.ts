import { useEffect, useState } from "react";

import type { PdfHighlight } from "./useSyncTex";

const SYNC_HIGHLIGHT_MS = 1200;

export type ShownHighlight = Pick<PdfHighlight, "page" | "box">;

/** Forward sync: jump to the target page and flash the box transiently. */
export function useSyncHighlight(
  syncTarget: PdfHighlight | null | undefined,
  setPage: (page: number) => void,
): ShownHighlight | null {
  const [highlight, setHighlight] = useState<ShownHighlight | null>(null);

  useEffect(() => {
    if (!syncTarget) return;
    setPage(syncTarget.page);
    setHighlight({ page: syncTarget.page, box: syncTarget.box });
    const timer = window.setTimeout(() => setHighlight(null), SYNC_HIGHLIGHT_MS);
    return () => window.clearTimeout(timer);
  }, [syncTarget, setPage]);

  return highlight;
}
