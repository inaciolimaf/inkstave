/**
 * The PDF preview pane (spec 24): Compile/Cancel button, PDF.js viewer with
 * zoom + page navigation, and a collapsible raw-log panel, with empty / loading
 * / error states for every compile outcome.
 */
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import i18n from "@/i18n/config";

import { getCompilePdf } from "./api";
import { CompileButton } from "./CompileButton";
import { CompileOutputDock } from "./CompileOutputDock";
import { PdfToolbar } from "./PdfToolbar";
import type { PageClickHandler } from "./PdfViewer";
import { type ErrorOutcome, PreviewBody } from "./PreviewBody";
import type { CompileProblems, ProblemsReason } from "./problems";
import type { PdfHighlight } from "./hooks/useSyncTex";
import { useCompile } from "./hooks/useCompile";
import { useCompileLog } from "./hooks/useCompileLog";
import { useOutputDock } from "./hooks/useOutputDock";
import { usePdfDocument } from "./hooks/usePdfDocument";
import { usePdfViewport } from "./hooks/usePdfViewport";
import { useSyncHighlight } from "./hooks/useSyncHighlight";
import { type CompileJobStatus, isActive, isTerminal } from "./types";

const ERROR_OUTCOMES = new Set<CompileJobStatus>(["failure", "timeout", "error"]);

function announce(status: string, progressLabel: string | null): string {
  if (progressLabel) return progressLabel;
  switch (status) {
    case "success":
      return i18n.t("preview:announce.succeeded");
    case "failure":
      return i18n.t("preview:announce.failed");
    case "timeout":
      return i18n.t("preview:announce.timedOut");
    case "cancelled":
      return i18n.t("preview:announce.cancelled");
    case "error":
      return i18n.t("preview:announce.error");
    default:
      return "";
  }
}

async function downloadPdf(projectId: string, compileId: string): Promise<void> {
  const bytes = await getCompilePdf(projectId, compileId);
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "output.pdf";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

interface PreviewPaneProps {
  projectId: string;
  /** Flush pending local CRDT edits before compiling (spec 31 §5.4); no-op when no session. */
  flush?: () => Promise<void>;
  /** Reports the compile id backing the shown PDF (or null) — drives sync availability. */
  onActiveCompileChange?: (compileId: string | null) => void;
  /** Double-click on a PDF page (inverse sync): page + PDF-point coordinates. */
  onPdfClick?: PageClickHandler;
  /** Forward-sync target: jump to the page and flash the box (spec 26). */
  syncTarget?: PdfHighlight | null;
  /** Reports the just-finished compile id when a compile reaches a terminal state. */
  onCompileResult?: (compileId: string | null) => void;
  /** Parsed problems for the current compile (spec 27), shown in the problems panel. */
  problems?: CompileProblems | null;
  problemsLoading?: boolean;
  problemsReason?: ProblemsReason | null;
  /** Click a problem row → jump to its source line. */
  onProblemJump?: (file: string, line: number) => void;
}

export function PreviewPane({
  projectId,
  flush,
  onActiveCompileChange,
  onPdfClick,
  syncTarget,
  onCompileResult,
  problems,
  problemsLoading,
  problemsReason,
  onProblemJump,
}: PreviewPaneProps) {
  const { t } = useTranslation("preview");
  const compile = useCompile(projectId, flush);
  const pdfDoc = usePdfDocument(projectId, compile.lastSuccessId);
  const viewport = usePdfViewport(pdfDoc.numPages);
  const logState = useCompileLog(projectId, compile.compileId);

  const errorOutcome = ERROR_OUTCOMES.has(compile.status as CompileJobStatus)
    ? (compile.status as ErrorOutcome)
    : null;
  const active = isActive(compile.status);
  const dock = useOutputDock(errorOutcome);

  // Report which compile the shown PDF belongs to (drives sync availability).
  useEffect(() => {
    onActiveCompileChange?.(compile.lastSuccessId);
  }, [compile.lastSuccessId, onActiveCompileChange]);

  // Report the finished compile so its problems can be (re)loaded.
  useEffect(() => {
    if (isTerminal(compile.status as CompileJobStatus)) onCompileResult?.(compile.compileId);
  }, [compile.status, compile.compileId, onCompileResult]);

  const highlight = useSyncHighlight(syncTarget, viewport.setPage);

  const showViewer = !errorOutcome && !active && !pdfDoc.loading && pdfDoc.pdf !== null;

  return (
    <div className="flex h-full flex-col" aria-label={t("pane.label")}>
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-1.5">
        <CompileButton
          state={compile.status}
          progressLabel={compile.progressLabel}
          onCompile={compile.compile}
          onCancel={compile.cancel}
        />
        {showViewer && (
          <div className="ml-auto">
            <PdfToolbar
              viewport={viewport}
              onDownload={
                compile.lastSuccessId ? () => void downloadPdf(projectId, compile.lastSuccessId!) : undefined
              }
            />
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1">
        <PreviewBody
          errorOutcome={errorOutcome}
          compile={compile}
          pdfDoc={pdfDoc}
          viewport={viewport}
          highlight={highlight}
          onViewLog={() => dock.showTab("log")}
          onPdfClick={onPdfClick}
        />
      </div>

      <p className="sr-only" role="status" aria-live="polite">
        {announce(compile.status, compile.progressLabel)}
      </p>

      <CompileOutputDock
        dock={dock}
        problems={problems ?? null}
        problemsLoading={problemsLoading}
        problemsReason={problemsReason}
        onProblemJump={onProblemJump}
        stale={active}
        logState={logState}
        meta={compile.meta}
      />
    </div>
  );
}
