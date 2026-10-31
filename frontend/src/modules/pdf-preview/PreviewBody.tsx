import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { PdfViewer, type PageClickHandler } from "./PdfViewer";
import { PreviewEmptyState } from "./PreviewEmptyState";
import { PreviewErrorState } from "./PreviewErrorState";
import type { UseCompile } from "./hooks/useCompile";
import type { PdfDocumentState } from "./hooks/usePdfDocument";
import type { PdfViewport } from "./hooks/usePdfViewport";
import type { ShownHighlight } from "./hooks/useSyncHighlight";
import { isActive } from "./types";

export type ErrorOutcome = "failure" | "timeout" | "error";

function Centered({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div
      className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-body text-muted-foreground"
      aria-label={label}
    >
      {children}
    </div>
  );
}

/** The main area of the pane: the compile error, a progress state, the PDF, or the empty state. */
export function PreviewBody({
  errorOutcome,
  compile,
  pdfDoc,
  viewport,
  highlight,
  onViewLog,
  onPdfClick,
}: {
  errorOutcome: ErrorOutcome | null;
  compile: UseCompile;
  pdfDoc: PdfDocumentState;
  viewport: PdfViewport;
  highlight: ShownHighlight | null;
  onViewLog: () => void;
  onPdfClick?: PageClickHandler;
}) {
  const { t } = useTranslation("preview");

  if (errorOutcome) {
    return (
      <PreviewErrorState
        outcome={errorOutcome}
        detail={compile.error}
        onViewLog={onViewLog}
        onRetry={compile.compile}
      />
    );
  }
  if (isActive(compile.status)) {
    return (
      <Centered label={t("compile.progressLabel")}>
        <Loader2 className="size-6 animate-spin" aria-hidden="true" />
        <p>{compile.progressLabel ?? t("compile.compiling")}</p>
      </Centered>
    );
  }
  if (pdfDoc.loading) {
    return (
      <Centered label={t("loading.loadingPdfLabel")}>
        <Loader2 className="size-6 animate-spin" aria-hidden="true" />
        <p>{t("loading.loadingPreview")}</p>
      </Centered>
    );
  }
  if (pdfDoc.error) {
    return (
      <Centered label={t("loading.pdfErrorLabel")}>
        <p className="text-error-text">{pdfDoc.error}</p>
      </Centered>
    );
  }
  if (pdfDoc.pdf) {
    return <PdfViewer pdf={pdfDoc.pdf} viewport={viewport} onPageClick={onPdfClick} highlight={highlight} />;
  }
  return <PreviewEmptyState />;
}
