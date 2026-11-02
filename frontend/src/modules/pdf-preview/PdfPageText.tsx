/** The page's invisible text over its canvas: what makes a PDF selectable and copyable. */
import { useEffect, useRef, type CSSProperties } from "react";

import { renderPageText, type PdfDocument, type PdfPage } from "./pdfjs";

export function PdfPageText({
  pdf,
  pageNumber,
  scale,
}: {
  pdf: PdfDocument;
  pageNumber: number;
  scale: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    let cancelRender: (() => void) | undefined;
    pdf.getPage(pageNumber).then((page: PdfPage) => {
      const container = ref.current;
      if (cancelled || !container) return;
      container.replaceChildren();
      cancelRender = renderPageText(page, container, scale);
    });
    return () => {
      cancelled = true;
      cancelRender?.();
    };
  }, [pdf, pageNumber, scale]);

  return (
    <div
      ref={ref}
      data-testid="pdf-text-layer"
      className="pdf-text-layer"
      style={{ "--scale-factor": scale } as CSSProperties}
      // While dragging, the end marker covers the page, so crossing a gap does not lose the selection.
      onPointerDown={(e) => e.currentTarget.classList.add("selecting")}
      onPointerUp={(e) => e.currentTarget.classList.remove("selecting")}
      onPointerCancel={(e) => e.currentTarget.classList.remove("selecting")}
    />
  );
}
