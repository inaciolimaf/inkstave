/**
 * Continuous PDF.js page renderer (spec 24, §5.3.4).
 *
 * Renders every page to its own canvas at the viewport scale. Fit modes measure
 * the container and push a computed scale back to the viewport. Navigation
 * scrolls the target page into view; scrolling reports the visible page back.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { PdfDocument, PdfPage } from "./pdfjs";
import type { PdfViewport } from "./hooks/usePdfViewport";
import type { SyncTexBox } from "./synctex";
import { boxToCssRect, cssToPdfPoint } from "./synctex-coords";

export type PageClickHandler = (page: number, hPdf: number, vPdf: number) => void;

function PdfPageView({
  pdf,
  pageNumber,
  scale,
  registerRef,
  onPageClick,
  highlight,
}: {
  pdf: PdfDocument;
  pageNumber: number;
  scale: number;
  registerRef: (el: HTMLDivElement | null) => void;
  onPageClick?: PageClickHandler;
  highlight?: SyncTexBox | null;
}) {
  const { t } = useTranslation("preview");
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const handleDoubleClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (!onPageClick) return;
      const rect = event.currentTarget.getBoundingClientRect();
      const { h, v } = cssToPdfPoint(event.clientX - rect.left, event.clientY - rect.top, scale);
      onPageClick(pageNumber, h, v);
    },
    [onPageClick, pageNumber, scale],
  );

  const overlay = highlight ? boxToCssRect(highlight, scale) : null;

  useEffect(() => {
    let cancelled = false;
    let task: { cancel: () => void; promise: Promise<void> } | null = null;
    pdf.getPage(pageNumber).then((page: PdfPage) => {
      if (cancelled) return;
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      const ctx = canvas.getContext("2d");
      if (!ctx) return; // jsdom / headless: no 2d context — skip pixel render
      task = page.render({ canvasContext: ctx, viewport });
      // Cancelling an in-flight render (scale/page change, unmount) rejects the
      // task promise with RenderingCancelledException — expected, so swallow it;
      // surface anything else.
      task.promise.catch((err: unknown) => {
        if ((err as { name?: string })?.name !== "RenderingCancelledException") throw err;
      });
    });
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [pdf, pageNumber, scale]);

  return (
    <div
      ref={registerRef}
      data-page={pageNumber}
      onDoubleClick={handleDoubleClick}
      className="relative mx-auto my-2 w-fit bg-white shadow"
      aria-label={t("viewer.page", { pageNumber })}
    >
      <canvas ref={canvasRef} className="block" />
      {overlay && (
        <div
          data-testid="sync-highlight"
          className="pointer-events-none absolute animate-pulse rounded-sm bg-amber-300/40 ring-2 ring-amber-400"
          style={{
            left: overlay.left,
            top: overlay.top,
            width: overlay.width,
            height: overlay.height,
          }}
        />
      )}
    </div>
  );
}

export function PdfViewer({
  pdf,
  viewport,
  onPageClick,
  highlight,
}: {
  pdf: PdfDocument;
  viewport: PdfViewport;
  onPageClick?: PageClickHandler;
  highlight?: { page: number; box: SyncTexBox } | null;
}) {
  const { t } = useTranslation("preview");
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Array<HTMLDivElement | null>>([]);
  const [containerWidth, setContainerWidth] = useState(0);
  const { numPages, scale, renderScale, fitMode, page, setScale, setPage } = viewport;
  // Render canvases at the debounced scale so a burst of zoom clicks coalesces
  // into one re-render (spec 24 §5.3.4); fall back to the live scale when a
  // caller supplies no debounced value.
  const drawScale = renderScale ?? scale;

  // Track the container width for fit-mode scale computation.
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    setContainerWidth(el.clientWidth);
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) setContainerWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Compute a fit scale from the first page's intrinsic size and push it up.
  useEffect(() => {
    if (fitMode === "none" || containerWidth <= 0) return;
    let cancelled = false;
    pdf.getPage(1).then((p: PdfPage) => {
      if (cancelled) return;
      const base = p.getViewport({ scale: 1 });
      const container = containerRef.current;
      if (!base.width || !container) return;
      const padding = 24;
      const widthScale = (containerWidth - padding) / base.width;
      const next =
        fitMode === "page" && base.height
          ? Math.min(widthScale, (container.clientHeight - padding) / base.height)
          : widthScale;
      if (Number.isFinite(next) && next > 0) setScale(next);
    });
    return () => {
      cancelled = true;
    };
  }, [pdf, fitMode, containerWidth, setScale]);

  // Scroll the requested page into view when navigation changes it.
  useEffect(() => {
    const el = pageRefs.current[page - 1];
    el?.scrollIntoView({ block: "start", behavior: "auto" });
  }, [page]);

  // Report the scroll-visible page back to the viewport.
  const onScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const top = container.scrollTop;
    let visible = 1;
    for (let i = 0; i < pageRefs.current.length; i++) {
      const el = pageRefs.current[i];
      if (el && el.offsetTop - container.offsetTop <= top + 8) visible = i + 1;
    }
    if (visible !== page) setPage(visible);
  }, [page, setPage]);

  pageRefs.current.length = numPages;

  return (
    <div
      ref={containerRef}
      onScroll={onScroll}
      role="document"
      aria-label={t("pane.pdfPreview")}
      className="h-full overflow-auto bg-muted/30 p-2"
    >
      {Array.from({ length: numPages }, (_, i) => (
        <PdfPageView
          key={i}
          pdf={pdf}
          pageNumber={i + 1}
          scale={drawScale}
          registerRef={(el) => {
            pageRefs.current[i] = el;
          }}
          onPageClick={onPageClick}
          highlight={highlight && highlight.page === i + 1 ? highlight.box : null}
        />
      ))}
    </div>
  );
}
