import { ChevronLeft, ChevronRight, Download, Maximize, MoveHorizontal, ZoomIn, ZoomOut } from "lucide-react";
import { type ComponentProps, type FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import type { PdfViewport } from "./hooks/usePdfViewport";

function ToolbarButton({
  label,
  className,
  variant = "ghost",
  ...props
}: ComponentProps<typeof Button> & { label: string }) {
  return (
    <Button size="icon" variant={variant} className={cn(className, "size-8")} aria-label={label} {...props} />
  );
}

function ZoomControls({ viewport }: { viewport: PdfViewport }) {
  const { t } = useTranslation("preview");
  return (
    <>
      <ToolbarButton label={t("toolbar.zoomOut")} onClick={viewport.zoomOut}>
        <ZoomOut aria-hidden="true" />
      </ToolbarButton>
      <span
        role="group"
        className="min-w-12 text-center text-small tabular-nums"
        aria-label={t("toolbar.zoomLevel")}
      >
        {viewport.zoomPercent}%
      </span>
      <ToolbarButton label={t("toolbar.zoomIn")} onClick={viewport.zoomIn}>
        <ZoomIn aria-hidden="true" />
      </ToolbarButton>
    </>
  );
}

function FitControls({ viewport }: { viewport: PdfViewport }) {
  const { t } = useTranslation("preview");
  const { fitMode } = viewport;
  return (
    <>
      <ToolbarButton
        label={t("toolbar.fitWidth")}
        variant={fitMode === "width" ? "secondary" : "ghost"}
        aria-pressed={fitMode === "width"}
        onClick={viewport.fitWidth}
      >
        <MoveHorizontal aria-hidden="true" />
      </ToolbarButton>
      <ToolbarButton
        label={t("toolbar.fitPage")}
        variant={fitMode === "page" ? "secondary" : "ghost"}
        aria-pressed={fitMode === "page"}
        onClick={viewport.fitPage}
      >
        <Maximize aria-hidden="true" />
      </ToolbarButton>
    </>
  );
}

function PageControls({ viewport }: { viewport: PdfViewport }) {
  const { t } = useTranslation("preview");
  const { page, numPages } = viewport;
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
    <>
      <ToolbarButton label={t("toolbar.previousPage")} onClick={viewport.goPrev} disabled={page <= 1}>
        <ChevronLeft aria-hidden="true" />
      </ToolbarButton>
      <form onSubmit={submitJump} className="flex items-center gap-1 text-small">
        <Input
          type="text"
          inputMode="numeric"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={submitJump}
          aria-label={t("toolbar.pageNumber")}
          className="h-7 w-12 px-1 text-center tabular-nums"
        />
        <span className="text-muted-foreground">{t("toolbar.of", { numPages })}</span>
      </form>
      <ToolbarButton label={t("toolbar.nextPage")} onClick={viewport.goNext} disabled={page >= numPages}>
        <ChevronRight aria-hidden="true" />
      </ToolbarButton>
    </>
  );
}

/** Zoom, fit, and page-navigation controls (spec 24, §5.3.5). */
export function PdfToolbar({ viewport, onDownload }: { viewport: PdfViewport; onDownload?: () => void }) {
  const { t } = useTranslation("preview");
  return (
    <div className="flex flex-wrap items-center gap-1">
      <ZoomControls viewport={viewport} />
      <FitControls viewport={viewport} />

      <span className="mx-1 h-5 w-px bg-border" aria-hidden="true" />

      <PageControls viewport={viewport} />

      {onDownload && (
        <ToolbarButton label={t("toolbar.downloadPdf")} className="ml-auto" onClick={onDownload}>
          <Download aria-hidden="true" />
        </ToolbarButton>
      )}
    </div>
  );
}
