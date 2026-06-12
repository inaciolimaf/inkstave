/**
 * Problems panel (spec 27): the parsed compile diagnostics grouped by severity,
 * each row a keyboard-navigable button that jumps to its source line.
 */
import { AlertCircle, AlertTriangle, ChevronRight, Info } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

import type { CompileProblems, Problem, ProblemSeverity } from "./problems";
import type { ProblemsReason } from "./problems";

const SEVERITY_ORDER: ProblemSeverity[] = ["error", "warning", "info"];

const SEVERITY_META: Record<
  ProblemSeverity,
  { label: string; Icon: typeof AlertCircle; className: string }
> = {
  error: { label: "Errors", Icon: AlertCircle, className: "text-destructive" },
  warning: { label: "Warnings", Icon: AlertTriangle, className: "text-amber-500" },
  info: { label: "Typesetting", Icon: Info, className: "text-sky-500" },
};

function ProblemRow({
  problem,
  onJump,
}: {
  problem: Problem;
  onJump?: (file: string, line: number) => void;
}) {
  const meta = SEVERITY_META[problem.severity];
  const locatable = problem.file != null && problem.line != null;
  const location = locatable ? `${problem.file}:${problem.line}` : null;
  return (
    <button
      type="button"
      disabled={!locatable || !onJump}
      onClick={() => locatable && onJump?.(problem.file!, problem.line!)}
      aria-label={`${problem.severity}: ${problem.message}${location ? ` (${location})` : ""}`}
      className="flex w-full items-start gap-2 px-3 py-1 text-left text-xs hover:bg-accent disabled:cursor-default disabled:hover:bg-transparent"
    >
      <meta.Icon className={cn("mt-0.5 size-3.5 shrink-0", meta.className)} aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate">{problem.message}</span>
      {location && <span className="shrink-0 font-mono text-muted-foreground">{location}</span>}
    </button>
  );
}

export function ProblemsPanel({
  problems,
  loading,
  reason,
  stale = false,
  onJump,
}: {
  problems: CompileProblems | null;
  loading?: boolean;
  reason?: ProblemsReason | null;
  /** A compile is running; the shown problems are from the previous result. */
  stale?: boolean;
  onJump?: (file: string, line: number) => void;
}) {
  const total = problems?.problems.length ?? 0;
  const [expanded, setExpanded] = useState(true);

  const counts = problems
    ? ([
        ["error", problems.errors] as const,
        ["warning", problems.warnings] as const,
        ["info", problems.infos] as const,
      ] satisfies [ProblemSeverity, number][])
    : [];

  let body: React.ReactNode;
  if (reason === "log_unavailable") {
    body = <p className="px-3 py-2 text-xs text-muted-foreground">No log yet — run a compile.</p>;
  } else if (total === 0) {
    body = <p className="px-3 py-2 text-xs text-muted-foreground">No problems.</p>;
  } else {
    body = SEVERITY_ORDER.map((severity) => {
      const group = problems!.problems.filter((p) => p.severity === severity);
      if (group.length === 0) return null;
      const meta = SEVERITY_META[severity];
      return (
        <div key={severity}>
          <p className="px-3 pt-1.5 pb-0.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            {meta.label} ({group.length})
          </p>
          {group.map((problem, i) => (
            <ProblemRow key={i} problem={problem} onJump={onJump} />
          ))}
        </div>
      );
    });
  }

  return (
    <div className="flex flex-col border-t">
      <div className="flex items-center gap-2 px-3 py-1.5">
        <button
          type="button"
          onClick={() => setExpanded((o) => !o)}
          aria-expanded={expanded}
          aria-controls="problems-region"
          className="flex items-center gap-1.5 text-sm font-medium hover:text-foreground/80"
        >
          <ChevronRight
            className={cn("size-4 transition-transform", expanded && "rotate-90")}
            aria-hidden="true"
          />
          Problems
        </button>
        {counts.map(([severity, count]) => {
          const meta = SEVERITY_META[severity];
          return (
            <span
              key={severity}
              className="flex items-center gap-0.5 text-xs text-muted-foreground"
              aria-label={`${count} ${severity}`}
            >
              <meta.Icon className={cn("size-3.5", meta.className)} aria-hidden="true" />
              {count}
            </span>
          );
        })}
        {(loading || stale) && (
          <span className="text-xs text-muted-foreground">{stale ? "updating…" : "loading…"}</span>
        )}
      </div>
      {expanded && (
        <div
          id="problems-region"
          role="region"
          aria-label="Compile problems"
          className="max-h-48 overflow-auto"
        >
          {body}
        </div>
      )}
    </div>
  );
}
