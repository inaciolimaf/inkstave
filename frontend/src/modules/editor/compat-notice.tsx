/** The template compatibility report: a notice in the status line, and the list it opens (spec 120). */
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { CompatFinding } from "@/modules/projects";

/** A dismissible line in the status bar: "3 things may not work in Inkstave". */
export function CompatNotice({
  count,
  onReview,
  onDismiss,
}: {
  count: number;
  onReview: () => void;
  onDismiss: () => void;
}) {
  const { t } = useTranslation("editor");
  return (
    <div role="status" className="flex min-w-0 items-center gap-2 text-small">
      <span className="truncate">{t("compat.notice", { count })}</span>
      <Button size="sm" variant="ghost" className="h-7 shrink-0 px-2" onClick={onReview}>
        {t("compat.review")}
      </Button>
      <Button size="sm" variant="ghost" className="h-7 shrink-0 px-2" onClick={onDismiss}>
        {t("compat.dismiss")}
      </Button>
    </div>
  );
}

/** Findings grouped by severity, warnings first. Each one opens its file at its line. */
function FindingGroup({
  title,
  findings,
  onOpenLine,
}: {
  title: string;
  findings: CompatFinding[];
  onOpenLine: (path: string, line: number) => void;
}) {
  if (findings.length === 0) return null;
  return (
    <section className="space-y-1">
      <h3 className="text-small font-medium text-muted-foreground">{title}</h3>
      <ul className="space-y-1">
        {findings.map((finding) => (
          <li key={`${finding.ruleId}:${finding.path}:${finding.line}`}>
            <button
              type="button"
              onClick={() => onOpenLine(finding.path, finding.line)}
              className="flex w-full min-w-0 flex-col items-start gap-0.5 rounded px-2 py-1.5 text-left hover:bg-accent"
            >
              <span className="font-mono text-small break-all">
                {finding.path}:{finding.line}
              </span>
              <span className="text-small text-muted-foreground">{finding.message}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function CompatReportDialog({
  open,
  onOpenChange,
  findings,
  onOpenLine,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  findings: CompatFinding[];
  onOpenLine: (path: string, line: number) => void;
}) {
  const { t } = useTranslation("editor");
  const warnings = findings.filter((f) => f.severity === "warning");
  const notes = findings.filter((f) => f.severity !== "warning");
  const pick = (path: string, line: number) => {
    onOpenChange(false);
    onOpenLine(path, line);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("compat.dialogTitle")}</DialogTitle>
          <DialogDescription>{t("compat.dialogDescription")}</DialogDescription>
        </DialogHeader>
        <FindingGroup title={t("compat.groupWarning")} findings={warnings} onOpenLine={pick} />
        <FindingGroup title={t("compat.groupInfo")} findings={notes} onOpenLine={pick} />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("compat.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
