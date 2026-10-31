/**
 * Problems panel (spec 27): the parsed compile diagnostics grouped by severity,
 * each row a keyboard-navigable button that jumps to its source line.
 *
 * The panel renders only the diagnostics region; the title, severity counts and
 * the collapse control live in the shared compile-output dock (see PreviewPane).
 */
import { AlertCircle, AlertTriangle, Info } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import type { CompileProblems, Problem, ProblemSeverity } from "./problems";
import type { ProblemsReason } from "./problems";

const SEVERITY_ORDER: ProblemSeverity[] = ["error", "warning", "info"];

const SEVERITY_META: Record<
  ProblemSeverity,
  { labelKey: string; Icon: typeof AlertCircle; className: string }
> = {
  error: { labelKey: "problems.errors", Icon: AlertCircle, className: "text-error-text" },
  warning: { labelKey: "problems.warnings", Icon: AlertTriangle, className: "text-warning-text" },
  info: { labelKey: "problems.typesetting", Icon: Info, className: "text-muted-foreground" },
};

function ProblemRow({
  problem,
  onJump,
  onAsk,
}: {
  problem: Problem;
  onJump?: (file: string, line: number) => void;
  onAsk?: (problem: Problem) => void;
}) {
  const { t } = useTranslation("preview");
  const meta = SEVERITY_META[problem.severity];
  const locatable = problem.file != null && problem.line != null;
  const location = locatable ? `${problem.file}:${problem.line}` : null;
  const row = (
    <button
      type="button"
      disabled={!locatable || !onJump}
      onClick={() => locatable && onJump?.(problem.file!, problem.line!)}
      aria-label={t("problems.rowLabel", {
        severity: problem.severity,
        message: problem.message,
        location: location ? ` (${location})` : "",
      })}
      className="flex w-full items-start gap-2 px-3 py-1 text-left text-small hover:bg-accent disabled:cursor-default disabled:hover:bg-transparent"
    >
      <meta.Icon className={cn("mt-0.5 size-3.5 shrink-0", meta.className)} aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate">{problem.message}</span>
      {location && <span className="shrink-0 font-mono text-muted-foreground">{location}</span>}
    </button>
  );
  if (!onAsk || problem.severity !== "error") return row;
  return (
    <div className="flex items-start">
      <div className="min-w-0 flex-1">{row}</div>
      <button
        type="button"
        onClick={() => onAsk(problem)}
        className="m-0.5 shrink-0 rounded border border-control-edge px-2 py-0.5 text-small font-medium hover:bg-accent"
      >
        {t("problems.askAgent")}
      </button>
    </div>
  );
}

/** Warnings can run to dozens of repeats: folded, they stop burying the one error. */
function QuietGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details>
      <summary className="cursor-pointer px-3 pb-0.5 pt-1.5 text-small font-medium text-muted-foreground">
        {title}
      </summary>
      {children}
    </details>
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
            className="flex items-center gap-0.5 text-small text-muted-foreground"
            role="img"
            aria-label={t("problems.countSeverity", { count, severity })}
          >
            <meta.Icon className={cn("size-3.5", meta.className)} aria-hidden="true" />
            {count}
          </span>
        );
      })}
      {(loading || stale) && (
        <span className="text-small text-muted-foreground">
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
  onAsk,
  foldQuiet = false,
}: {
  problems: CompileProblems | null;
  reason?: ProblemsReason | null;
  onJump?: (file: string, line: number) => void;
  onAsk?: (problem: Problem) => void;
  /** Fold everything below an error, for the dock that floats over the text. */
  foldQuiet?: boolean;
}) {
  const { t } = useTranslation("preview");
  const total = problems?.problems.length ?? 0;

  let body: React.ReactNode;
  if (reason === "log_unavailable") {
    body = <p className="px-3 py-2 text-small text-muted-foreground">{t("problems.noLogYet")}</p>;
  } else if (total === 0) {
    body = <p className="px-3 py-2 text-small text-muted-foreground">{t("problems.noProblems")}</p>;
  } else {
    body = SEVERITY_ORDER.map((severity) => {
      const group = problems!.problems.filter((p) => p.severity === severity);
      if (group.length === 0) return null;
      const meta = SEVERITY_META[severity];
      const title = t("problems.group", { label: t(meta.labelKey), count: group.length });
      const rows = group.map((problem, i) => (
        <ProblemRow key={i} problem={problem} onJump={onJump} onAsk={onAsk} />
      ));
      if (foldQuiet && severity !== "error") {
        return (
          <QuietGroup key={severity} title={title}>
            {rows}
          </QuietGroup>
        );
      }
      return (
        <div key={severity}>
          <p className="px-3 pt-1.5 pb-0.5 text-small font-medium text-muted-foreground">{title}</p>
          {rows}
        </div>
      );
    });
  }

  return (
    <div
      id="problems-region"
      role="region"
      aria-label={t("problems.region")}
      className={foldQuiet ? "max-h-[50dvh] overflow-auto py-1" : "max-h-48 overflow-auto"}
    >
      {body}
    </div>
  );
}
