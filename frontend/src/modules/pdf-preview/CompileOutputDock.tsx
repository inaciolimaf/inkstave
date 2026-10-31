import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import { LogPanel } from "./LogPanel";
import { ProblemsPanel, ProblemsSummary } from "./ProblemsPanel";
import type { CompileLogState } from "./hooks/useCompileLog";
import type { OutputDock } from "./hooks/useOutputDock";
import type { CompileProblems, ProblemsReason } from "./problems";
import type { CompileStatus } from "./types";

function CollapseButton({ dock }: { dock: OutputDock }) {
  const { t } = useTranslation("preview");
  return (
    <button
      type="button"
      onClick={dock.toggleCollapsed}
      aria-expanded={!dock.collapsed}
      aria-controls="compile-output-panels"
      aria-label={dock.collapsed ? t("pane.expandOutput") : t("pane.collapseOutput")}
      className="rounded p-1 text-muted-foreground hover:text-foreground/80"
    >
      <ChevronRight
        className={cn("size-4 transition-transform duration-fast", !dock.collapsed && "rotate-90")}
        aria-hidden="true"
      />
    </button>
  );
}

function OutputTabs({ dock }: { dock: OutputDock }) {
  const { t } = useTranslation("preview");
  return (
    <div role="tablist" aria-label={t("pane.compileOutput")} className="flex items-center">
      {(["problems", "log"] as const).map((tab) => (
        <button
          key={tab}
          type="button"
          role="tab"
          id={`compile-tab-${tab}`}
          aria-selected={!dock.collapsed && dock.tab === tab}
          aria-controls={`compile-panel-${tab}`}
          onClick={() => dock.showTab(tab)}
          className={
            !dock.collapsed && dock.tab === tab
              ? "border-b-2 border-primary px-2 py-1.5 text-body font-medium"
              : "border-b-2 border-transparent px-2 py-1.5 text-body text-muted-foreground hover:text-foreground/80"
          }
        >
          {tab === "problems" ? t("problems.title") : t("log.title")}
        </button>
      ))}
    </div>
  );
}

/** Problems and the raw log share one collapsible tabbed dock (spec 27 §5.3). */
export function CompileOutputDock({
  dock,
  problems,
  problemsLoading,
  problemsReason,
  onProblemJump,
  stale,
  logState,
  meta,
}: {
  dock: OutputDock;
  problems: CompileProblems | null;
  problemsLoading?: boolean;
  problemsReason?: ProblemsReason | null;
  onProblemJump?: (file: string, line: number) => void;
  /** A compile is running, so the counts describe the previous one. */
  stale: boolean;
  logState: CompileLogState;
  meta: CompileStatus | null;
}) {
  return (
    <div className="flex flex-col border-t">
      <div className="flex items-center gap-1 px-2">
        <CollapseButton dock={dock} />
        <OutputTabs dock={dock} />
        {/* Severity counts stay visible even when the dock is collapsed. */}
        <div className="ml-auto flex items-center gap-2 pr-1">
          <ProblemsSummary problems={problems} loading={problemsLoading} stale={stale} />
        </div>
      </div>
      {!dock.collapsed && (
        <div id="compile-output-panels">
          <div
            role="tabpanel"
            id="compile-panel-problems"
            aria-labelledby="compile-tab-problems"
            hidden={dock.tab !== "problems"}
          >
            <ProblemsPanel problems={problems} reason={problemsReason} onJump={onProblemJump} />
          </div>
          <div
            role="tabpanel"
            id="compile-panel-log"
            aria-labelledby="compile-tab-log"
            hidden={dock.tab !== "log"}
          >
            <LogPanel
              expanded={dock.tab === "log"}
              log={logState.log}
              loading={logState.loading}
              error={logState.error}
              onFetch={logState.fetchLog}
              meta={meta}
            />
          </div>
        </div>
      )}
    </div>
  );
}
