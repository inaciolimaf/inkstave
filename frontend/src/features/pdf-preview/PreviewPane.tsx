/**
 * The PDF preview pane (spec 24): Compile/Cancel button, PDF.js viewer with
 * zoom + page navigation, and a collapsible raw-log panel, with empty / loading
 * / error states for every compile outcome.
 */
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { getCompilePdf } from "./api";
import { CompileButton } from "./CompileButton";
import { LogPanel } from "./LogPanel";
import { PdfToolbar } from "./PdfToolbar";
import { PdfViewer, type PageClickHandler } from "./PdfViewer";
import { PreviewEmptyState } from "./PreviewEmptyState";
import { PreviewErrorState } from "./PreviewErrorState";
import { ProblemsPanel } from "./ProblemsPanel";
import type { CompileProblems, ProblemsReason } from "./problems";
import type { PdfHighlight } from "./hooks/useSyncTex";
import { useCompile } from "./hooks/useCompile";
import { useCompileLog } from "./hooks/useCompileLog";
import { usePdfDocument } from "./hooks/usePdfDocument";
import { usePdfViewport } from "./hooks/usePdfViewport";
import { type CompileJobStatus, isActive, isTerminal } from "./types";

const SYNC_HIGHLIGHT_MS = 1200;

const ERROR_OUTCOMES = new Set<CompileJobStatus>(["failure", "timeout", "error"]);

function announce(status: string, progressLabel: string | null): string {
  if (progressLabel) return progressLabel;
  switch (status) {
    case "success":
      return "Compilation succeeded.";
    case "failure":
      return "Compilation failed.";
    case "timeout":
      return "Compilation timed out.";
    case "cancelled":
      return "Compilation cancelled.";
    case "error":
      return "Compilation error.";
    default:
      return "";
  }
}

function Centered({ children, label }: { children: React.ReactNode; label?: string }) {
  return (
    <div
      className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground"
      aria-label={label}
    >
      {children}
    </div>
  );
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
}: {
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
}) {
  const compile = useCompile(projectId, flush);
  const pdfDoc = usePdfDocument(projectId, compile.lastSuccessId);
  const viewport = usePdfViewport(pdfDoc.numPages);
  const logState = useCompileLog(projectId, compile.compileId);
  const [bottomTab, setBottomTab] = useState<"problems" | "log">("problems");
  const [highlight, setHighlight] = useState<{ page: number; box: PdfHighlight["box"] } | null>(
    null,
  );

  const errorOutcome = ERROR_OUTCOMES.has(compile.status as CompileJobStatus)
    ? (compile.status as "failure" | "timeout" | "error")
    : null;
  const active = isActive(compile.status);

  // Switch to the Log tab on a failed/timed-out/errored compile (§5.3.6).
  useEffect(() => {
    if (errorOutcome) setBottomTab("log");
  }, [errorOutcome]);

  // Report which compile the shown PDF belongs to (drives sync availability).
  useEffect(() => {
    onActiveCompileChange?.(compile.lastSuccessId);
  }, [compile.lastSuccessId, onActiveCompileChange]);

  // Report the finished compile so its problems can be (re)loaded.
  useEffect(() => {
    if (isTerminal(compile.status as CompileJobStatus)) onCompileResult?.(compile.compileId);
  }, [compile.status, compile.compileId, onCompileResult]);

  // Forward sync: jump to the target page and flash the box transiently.
  const setPage = viewport.setPage;
  useEffect(() => {
    if (!syncTarget) return;
    setPage(syncTarget.page);
    setHighlight({ page: syncTarget.page, box: syncTarget.box });
    const timer = window.setTimeout(() => setHighlight(null), SYNC_HIGHLIGHT_MS);
    return () => window.clearTimeout(timer);
  }, [syncTarget, setPage]);

  const showViewer = !errorOutcome && !active && !pdfDoc.loading && pdfDoc.pdf !== null;

  let body: React.ReactNode;
  if (errorOutcome) {
    body = (
      <PreviewErrorState
        outcome={errorOutcome}
        detail={compile.error}
        onViewLog={() => setBottomTab("log")}
        onRetry={compile.compile}
      />
    );
  } else if (active) {
    body = (
      <Centered label="Compiling">
        <Loader2 className="size-6 animate-spin" aria-hidden="true" />
        <p>{compile.progressLabel ?? "Compiling…"}</p>
      </Centered>
    );
  } else if (pdfDoc.loading) {
    body = (
      <Centered label="Loading PDF">
        <Loader2 className="size-6 animate-spin" aria-hidden="true" />
        <p>Loading preview…</p>
      </Centered>
    );
  } else if (pdfDoc.error) {
    body = (
      <Centered label="PDF error">
        <p className="text-destructive">{pdfDoc.error}</p>
      </Centered>
    );
  } else if (pdfDoc.pdf) {
    body = (
      <PdfViewer
        pdf={pdfDoc.pdf}
        viewport={viewport}
        onPageClick={onPdfClick}
        highlight={highlight}
      />
    );
  } else {
    body = <PreviewEmptyState />;
  }

  return (
    <div className="flex h-full flex-col" aria-label="PDF preview pane">
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
                compile.lastSuccessId
                  ? () => void downloadPdf(projectId, compile.lastSuccessId!)
                  : undefined
              }
            />
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1">{body}</div>

      <p className="sr-only" role="status" aria-live="polite">
        {announce(compile.status, compile.progressLabel)}
      </p>

      {/* Problems and the raw log share one tabbed region (spec 27 §5.3). */}
      <div className="flex flex-col border-t">
        <div role="tablist" aria-label="Compile output" className="flex items-center gap-1 px-2">
          {(["problems", "log"] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              id={`compile-tab-${tab}`}
              aria-selected={bottomTab === tab}
              aria-controls={`compile-panel-${tab}`}
              onClick={() => setBottomTab(tab)}
              className={
                bottomTab === tab
                  ? "border-b-2 border-primary px-2 py-1.5 text-sm font-medium"
                  : "border-b-2 border-transparent px-2 py-1.5 text-sm text-muted-foreground hover:text-foreground/80"
              }
            >
              {tab === "problems" ? "Problems" : "Log"}
            </button>
          ))}
        </div>
        <div
          role="tabpanel"
          id="compile-panel-problems"
          aria-labelledby="compile-tab-problems"
          hidden={bottomTab !== "problems"}
        >
          <ProblemsPanel
            problems={problems ?? null}
            loading={problemsLoading}
            reason={problemsReason}
            stale={active}
            onJump={onProblemJump}
          />
        </div>
        <div
          role="tabpanel"
          id="compile-panel-log"
          aria-labelledby="compile-tab-log"
          hidden={bottomTab !== "log"}
        >
          <LogPanel
            expanded={bottomTab === "log"}
            onToggle={() => setBottomTab((t) => (t === "log" ? "problems" : "log"))}
            log={logState.log}
            loading={logState.loading}
            error={logState.error}
            onFetch={logState.fetchLog}
            meta={compile.meta}
          />
        </div>
      </div>
    </div>
  );
}
