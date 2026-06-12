import {
  ChevronLeft,
  ChevronRight,
  Download,
  Maximize,
  MoveHorizontal,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import type { PdfViewport } from "./hooks/usePdfViewport";

/** Zoom, fit, and page-navigation controls (spec 24, §5.3.5). */
export function PdfToolbar({
  viewport,
  onDownload,
}: {
  viewport: PdfViewport;
  onDownload?: () => void;
}) {
  const { page, numPages, zoomPercent, fitMode } = viewport;
  const [draft, setDraft] = useState(String(page));

  // Keep the jump input in sync with programmatic page changes (prev/next/scroll).
  useEffect(() => setDraft(String(page)), [page]);

  const submitJump = (e: FormEvent) => {
    e.preventDefault();
    const n = Number(draft);
    if (Number.isFinite(n)) viewport.jumpTo(Math.trunc(n));
    else setDraft(String(page));
  };

  return (
    <div className="flex flex-wrap items-center gap-1">
      <Button
        size="icon"
        variant="ghost"
        className="size-8"
        aria-label="Zoom out"
        onClick={viewport.zoomOut}
      >
        <ZoomOut aria-hidden="true" />
      </Button>
      <span className="min-w-12 text-center text-xs tabular-nums" aria-label="Zoom level">
        {zoomPercent}%
      </span>
      <Button
        size="icon"
        variant="ghost"
        className="size-8"
        aria-label="Zoom in"
        onClick={viewport.zoomIn}
      >
        <ZoomIn aria-hidden="true" />
      </Button>
      <Button
        size="icon"
        variant={fitMode === "width" ? "secondary" : "ghost"}
        className="size-8"
        aria-label="Fit width"
        aria-pressed={fitMode === "width"}
        onClick={viewport.fitWidth}
      >
        <MoveHorizontal aria-hidden="true" />
      </Button>
      <Button
        size="icon"
        variant={fitMode === "page" ? "secondary" : "ghost"}
        className="size-8"
        aria-label="Fit page"
        aria-pressed={fitMode === "page"}
        onClick={viewport.fitPage}
      >
        <Maximize aria-hidden="true" />
      </Button>

      <span className="mx-1 h-5 w-px bg-border" aria-hidden="true" />

      <Button
        size="icon"
        variant="ghost"
        className="size-8"
        aria-label="Previous page"
        onClick={viewport.goPrev}
        disabled={page <= 1}
      >
        <ChevronLeft aria-hidden="true" />
      </Button>
      <form onSubmit={submitJump} className="flex items-center gap-1 text-xs">
        <Input
          type="text"
          inputMode="numeric"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={submitJump}
          aria-label="Page number"
          className="h-7 w-12 px-1 text-center tabular-nums"
        />
        <span className="text-muted-foreground">of {numPages}</span>
      </form>
      <Button
        size="icon"
        variant="ghost"
        className="size-8"
        aria-label="Next page"
        onClick={viewport.goNext}
        disabled={page >= numPages}
      >
        <ChevronRight aria-hidden="true" />
      </Button>

      {onDownload && (
        <Button
          size="icon"
          variant="ghost"
          className="ml-auto size-8"
          aria-label="Download PDF"
          onClick={onDownload}
        >
          <Download aria-hidden="true" />
        </Button>
      )}
    </div>
  );
}
