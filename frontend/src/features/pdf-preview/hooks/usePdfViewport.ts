/**
 * Zoom + page-navigation state shared by `PdfToolbar` and `PdfViewer`
 * (spec 24, §5.3.5). The toolbar drives the actions; the viewer reads `scale`
 * and `page`, reports the scroll-visible page back via `setPage`, and reports a
 * computed fit scale via `setScale` while `fitMode` stays active.
 */
import { useCallback, useEffect, useState } from "react";

export type FitMode = "none" | "width" | "page";

export const MIN_SCALE = 0.25;
export const MAX_SCALE = 4;
const ZOOM_STEP = 1.2;
/** Coalesce rapid zoom clicks into one canvas re-render (spec 24 §5.3.4). */
export const ZOOM_DEBOUNCE_MS = 120;

function clampScale(scale: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
}

export interface PdfViewport {
  scale: number;
  /**
   * `scale` debounced so rapid zoom clicks coalesce into a single re-render
   * (spec 24 §5.3.4). Optional so callers/tests that only care about the live
   * scale can omit it; the viewer falls back to `scale` when it is absent.
   */
  renderScale?: number;
  fitMode: FitMode;
  page: number;
  numPages: number;
  zoomPercent: number;
  zoomIn: () => void;
  zoomOut: () => void;
  fitWidth: () => void;
  fitPage: () => void;
  setScale: (scale: number) => void;
  setPage: (page: number) => void;
  goPrev: () => void;
  goNext: () => void;
  jumpTo: (page: number) => void;
}

export function usePdfViewport(numPages: number): PdfViewport {
  const [scale, setScaleState] = useState(1);
  const [renderScale, setRenderScale] = useState(1);
  const [fitMode, setFitMode] = useState<FitMode>("width");
  const [page, setPageState] = useState(1);

  // A freshly loaded document resets navigation to the first page.
  useEffect(() => {
    setPageState(1);
  }, [numPages]);

  // Debounce the rendered scale so a burst of zoom clicks collapses into one
  // canvas re-render (spec 24 §5.3.4) instead of one per intermediate step.
  useEffect(() => {
    const id = setTimeout(() => setRenderScale(scale), ZOOM_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [scale]);

  const clampPage = useCallback(
    (p: number) => Math.min(Math.max(1, p), Math.max(1, numPages)),
    [numPages],
  );

  const zoomIn = useCallback(() => {
    setFitMode("none");
    setScaleState((s) => clampScale(s * ZOOM_STEP));
  }, []);
  const zoomOut = useCallback(() => {
    setFitMode("none");
    setScaleState((s) => clampScale(s / ZOOM_STEP));
  }, []);
  const fitWidth = useCallback(() => setFitMode("width"), []);
  const fitPage = useCallback(() => setFitMode("page"), []);

  // Used by the viewer to push a computed fit scale without leaving fit mode.
  const setScale = useCallback((s: number) => setScaleState(clampScale(s)), []);

  const setPage = useCallback((p: number) => setPageState(clampPage(p)), [clampPage]);
  const goPrev = useCallback(() => setPageState((p) => clampPage(p - 1)), [clampPage]);
  const goNext = useCallback(() => setPageState((p) => clampPage(p + 1)), [clampPage]);
  const jumpTo = useCallback((p: number) => setPageState(clampPage(p)), [clampPage]);

  return {
    scale,
    renderScale,
    fitMode,
    page,
    numPages,
    zoomPercent: Math.round(scale * 100),
    zoomIn,
    zoomOut,
    fitWidth,
    fitPage,
    setScale,
    setPage,
    goPrev,
    goNext,
    jumpTo,
  };
}
