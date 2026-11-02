/**
 * Thin PDF.js wrapper (spec 24).
 *
 * Isolating `pdfjs-dist` behind this module means:
 *  - the worker is configured in exactly one place, and
 *  - tests mock `@/modules/pdf-preview/pdfjs` instead of importing the real
 *    (heavy, jsdom-unfriendly) library.
 *
 * Worker setup uses Vite's `?url` import so the bundler emits the worker as a
 * separate asset and gives us its final URL (see `docs/adr/0024-pdf-preview.md`).
 */
import {
  GlobalWorkerOptions,
  TextLayer,
  getDocument,
  type PDFDocumentProxy,
  type PDFPageProxy,
} from "pdfjs-dist";
// Vite emits the worker as a separate asset and gives us its URL.
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

GlobalWorkerOptions.workerSrc = workerUrl;

export type PdfDocument = PDFDocumentProxy;
export type PdfPage = PDFPageProxy;

/** Load a PDF document from raw bytes. */
export async function loadPdfDocument(data: ArrayBuffer): Promise<PdfDocument> {
  // PDF.js may transfer/detach the buffer; hand it a copy so the caller's
  // ArrayBuffer stays usable (e.g. for a retry).
  return getDocument({ data: data.slice(0) }).promise;
}

/** Fill `container` with the page's selectable text; returns what stops it. */
export function renderPageText(page: PdfPage, container: HTMLElement, scale: number): () => void {
  const layer = new TextLayer({
    textContentSource: page.streamTextContent({ includeMarkedContent: true, disableNormalization: true }),
    container,
    viewport: page.getViewport({ scale }),
  });
  layer
    .render()
    .then(() => {
      const end = document.createElement("div");
      end.className = "endOfContent";
      container.append(end);
    })
    .catch((err: unknown) => {
      // A new scale or an unmount cancels the render, which is expected.
      if ((err as { name?: string })?.name !== "AbortException") throw err;
    });
  return () => layer.cancel();
}
