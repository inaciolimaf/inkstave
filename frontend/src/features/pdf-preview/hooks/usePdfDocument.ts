/**
 * Load + manage the PDF.js document for a successful compile (spec 24, §5.3.4).
 *
 * The PDF is fetched as bytes through the authed API client (see api.ts) and
 * handed to PDF.js. When `compileId` changes, the previous document is destroyed
 * before the next loads, so a re-compile never leaves a stale/broken canvas.
 */
import { useEffect, useState } from "react";

import i18n from "@/i18n/config";

import { getCompilePdf } from "../api";
import { type PdfDocument, loadPdfDocument } from "../pdfjs";

export interface PdfDocumentState {
  pdf: PdfDocument | null;
  numPages: number;
  loading: boolean;
  error: string | null;
}

const EMPTY: PdfDocumentState = { pdf: null, numPages: 0, loading: false, error: null };

export function usePdfDocument(projectId: string, compileId: string | null): PdfDocumentState {
  const [state, setState] = useState<PdfDocumentState>(EMPTY);

  useEffect(() => {
    if (!compileId) {
      setState(EMPTY);
      return;
    }
    let cancelled = false;
    let loaded: PdfDocument | null = null;
    setState((s) => ({ ...s, loading: true, error: null }));

    getCompilePdf(projectId, compileId)
      .then((bytes) => loadPdfDocument(bytes))
      .then((pdf) => {
        if (cancelled) {
          void pdf.destroy();
          return;
        }
        loaded = pdf;
        setState({ pdf, numPages: pdf.numPages, loading: false, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({
          pdf: null,
          numPages: 0,
          loading: false,
          error: err instanceof Error ? err.message : i18n.t("preview:errors.loadPdf"),
        });
      });

    return () => {
      cancelled = true;
      if (loaded) void loaded.destroy();
    };
  }, [projectId, compileId]);

  return state;
}
