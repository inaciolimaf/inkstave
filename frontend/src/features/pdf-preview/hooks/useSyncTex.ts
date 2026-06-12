/**
 * SyncTeX orchestration (spec 26): turn forward/inverse requests into a PDF
 * highlight target (forward) or a resolved source location (inverse), toasting
 * the `synctex_unavailable` / `no_match` cases so callers stay simple.
 */
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";

import {
  type InverseResult,
  type SyncReason,
  type SyncTexBox,
  codeToPdf,
  pdfToCode,
} from "../synctex";

export interface PdfHighlight {
  page: number;
  box: SyncTexBox;
  /** Bumped on each forward sync so the viewer re-triggers even for the same box. */
  nonce: number;
}

function toastReason(reason: SyncReason): void {
  if (reason === "synctex_unavailable") {
    toast.message("SyncTeX data not available for this compile");
  } else if (reason === "no_match") {
    toast.message("No matching location");
  } else {
    toast.error("Sync failed");
  }
}

export interface UseSyncTex {
  pdfTarget: PdfHighlight | null;
  clearPdfTarget: () => void;
  /** Forward (editor -> PDF): resolve the cursor line to a PDF box + highlight it. */
  syncFromSource: (file: string, line: number) => Promise<void>;
  /** Inverse (PDF -> editor): resolve a PDF point to a source location. */
  syncFromPdf: (page: number, h: number, v: number) => Promise<InverseResult | null>;
}

export function useSyncTex(projectId: string, compileId: string | null): UseSyncTex {
  const [pdfTarget, setPdfTarget] = useState<PdfHighlight | null>(null);
  const nonce = useRef(0);

  const syncFromSource = useCallback(
    async (file: string, line: number) => {
      const result = await codeToPdf(projectId, {
        file,
        line,
        compileId: compileId ?? undefined,
      });
      if (!result.ok) {
        toastReason(result.reason);
        return;
      }
      const box = result.value.boxes[0];
      if (!box) {
        toast.message("No matching location");
        return;
      }
      nonce.current += 1;
      setPdfTarget({ page: box.page, box, nonce: nonce.current });
    },
    [projectId, compileId],
  );

  const syncFromPdf = useCallback(
    async (page: number, h: number, v: number): Promise<InverseResult | null> => {
      const result = await pdfToCode(projectId, { page, h, v, compileId: compileId ?? undefined });
      if (!result.ok) {
        toastReason(result.reason);
        return null;
      }
      return result.value;
    },
    [projectId, compileId],
  );

  const clearPdfTarget = useCallback(() => setPdfTarget(null), []);

  return { pdfTarget, clearPdfTarget, syncFromSource, syncFromPdf };
}
