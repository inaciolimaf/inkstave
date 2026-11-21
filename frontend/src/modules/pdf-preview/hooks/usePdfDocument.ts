/**
 * Load + manage the PDF.js document for a successful compile (spec 24, §5.3.4).
 *
 * The PDF is fetched as bytes through the authed API client (see api.ts) and
 * handed to PDF.js. When `compileId` changes, the previous document is destroyed
 * before the next loads, so a re-compile never leaves a stale/broken canvas.
 */
import { useEffect, useState } from "react";

import i18n from "@/i18n/config";

import { getCompilePdf, getProjectFileBytes } from "../api";
import { type PdfDocument, loadPdfDocument } from "../pdfjs";

export interface PdfDocumentState {
  pdf: PdfDocument | null;
  numPages: number;
  loading: boolean;
  error: string | null;
}

const EMPTY: PdfDocumentState = { pdf: null, numPages: 0, loading: false, error: null };

export function usePdfDocument(projectId: string, compileId: string | null): PdfDocumentState {
  return useLoadedPdf(compileId ? `${projectId}/${compileId}` : null, () =>
    getCompilePdf(projectId, compileId ?? ""),
  );
}

/** A project file that is a PDF, for viewing in the editor pane. */
export function useProjectFilePdf(projectId: string, entityId: string): PdfDocumentState {
  return useLoadedPdf(`${projectId}/files/${entityId}`, () => getProjectFileBytes(projectId, entityId));
}

/** Load the PDF whose bytes `fetchBytes` returns, again whenever `key` changes; `null` loads nothing. */
function useLoadedPdf(key: string | null, fetchBytes: () => Promise<ArrayBuffer>): PdfDocumentState {
  const [state, setState] = useState<PdfDocumentState>(EMPTY);

  useEffect(() => {
    if (!key) {
      setState(EMPTY);
      return;
    }
    let cancelled = false;
    let loaded: PdfDocument | null = null;
    setState((s) => ({ ...s, loading: true, error: null }));

    fetchBytes()
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
    // `fetchBytes` is a fresh closure each render; `key` names what it fetches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return state;
}
