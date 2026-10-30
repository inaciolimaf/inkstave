/**
 * Problems panel (spec 27): the parsed compile diagnostics grouped by severity,
 * each row a keyboard-navigable button that jumps to its source line.
 *
 * The panel renders only the diagnostics region; the title, severity counts and
 * the collapse control live in the shared compile-output dock (see PreviewPane).
 */
import { AlertCircle, AlertTriangle, Info } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import type { CompileProblems, Problem, ProblemSeverity } from "./problems";
import type { ProblemsReason } from "./problems";

const SEVERITY_ORDER: ProblemSeverity[] = ["error", "warning", "info"];

const SEVERITY_META: Record<
  ProblemSeverity,
  { labelKey: string; Icon: typeof AlertCircle; className: string }
> = {
  error: { labelKey: "problems.errors", Icon: AlertCircle, className: "text-destructive" },
  warning: { labelKey: "problems.warnings", Icon: AlertTriangle, className: "text-amber-500" },
  info: { labelKey: "problems.typesetting", Icon: Info, className: "text-sky-500" },
};

function ProblemRow({
  problem,
  onJump,
}: {
  problem: Problem;
  onJump?: (file: string, line: number) => void;
}) {
  const { t } = useTranslation("preview");
  const meta = SEVERITY_META[problem.severity];
  const locatable = problem.file != null && problem.line != null;
  const location = locatable ? `${problem.file}:${problem.line}` : null;
  return (
    <button
      type="button"
      disabled={!locatable || !onJump}
      onClick={() => locatable && onJump?.(problem.file!, problem.line!)}
      aria-label={t("problems.rowLabel", {
        severity: problem.severity,
        message: problem.message,
        location: location ? ` (${location})` : "",
      })}
      className="flex w-full items-start gap-2 px-3 py-1 text-left text-xs hover:bg-accent disabled:cursor-default disabled:hover:bg-transparent"
    >
      <meta.Icon className={cn("mt-0.5 size-3.5 shrink-0", meta.className)} aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate">{problem.message}</span>
      {location && <span className="shrink-0 font-mono text-muted-foreground">{location}</span>}
    </button>
  );
}

/**
 * Compact severity counts shown in the compile-output tab bar; stays visible
 * even when the dock is collapsed so problem totals are always at a glance.
 */
export function ProblemsSummary({
  problems,
  loading = false,
  stale = false,
}: {
  problems: CompileProblems | null;
  loading?: boolean;
  /** A compile is running; the shown counts are from the previous result. */
  stale?: boolean;
}) {
  const { t } = useTranslation("preview");
  const counts = problems
    ? ([
        ["error", problems.errors] as const,
        ["warning", problems.warnings] as const,
        ["info", problems.infos] as const,
      ] satisfies [ProblemSeverity, number][])
    : [];

  return (
    <>
      {counts.map(([severity, count]) => {
        const meta = SEVERITY_META[severity];
        return (
          <span
            key={severity}
            className="flex items-center gap-0.5 text-xs text-muted-foreground"
            aria-label={t("problems.countSeverity", { count, severity })}
          >
            <meta.Icon className={cn("size-3.5", meta.className)} aria-hidden="true" />
            {count}
          </span>
        );
      })}
      {(loading || stale) && (
        <span className="text-xs text-muted-foreground">
          {stale ? t("problems.updating") : t("problems.loading")}
        </span>
      )}
    </>
  );
}

export function ProblemsPanel({
  problems,
  reason,
  onJump,
}: {
  problems: CompileProblems | null;
  reason?: ProblemsReason | null;
  onJump?: (file: string, line: number) => void;
}) {
  const { t } = useTranslation("preview");
  const total = problems?.problems.length ?? 0;

  let body: React.ReactNode;
  if (reason === "log_unavailable") {
    body = <p className="px-3 py-2 text-xs text-muted-foreground">{t("problems.noLogYet")}</p>;
  } else if (total === 0) {
    body = <p className="px-3 py-2 text-xs text-muted-foreground">{t("problems.noProblems")}</p>;
  } else {
    body = SEVERITY_ORDER.map((severity) => {
      const group = problems!.problems.filter((p) => p.severity === severity);
      if (group.length === 0) return null;
      const meta = SEVERITY_META[severity];
      return (
        <div key={severity}>
          <p className="px-3 pt-1.5 pb-0.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            {t("problems.group", { label: t(meta.labelKey), count: group.length })}
          </p>
          {group.map((problem, i) => (
            <ProblemRow key={i} problem={problem} onJump={onJump} />
          ))}
        </div>
      );
    });
  }

  return (
    <div
      id="problems-region"
      role="region"
      aria-label={t("problems.region")}
      className="max-h-48 overflow-auto"
    >
      {body}
    </div>
  );
}
