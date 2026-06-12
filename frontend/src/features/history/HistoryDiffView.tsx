/** Renders the spec-37 diff hunks with added/removed markers (spec 38). */
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import type { DiffHunk, LabelBrief, SegmentType } from "./types";
import { useDiff } from "./useHistory";

const MARKER: Record<SegmentType, string> = { added: "+", removed: "-", context: " " };
const ROW_CLASS: Record<SegmentType, string> = {
  added: "bg-green-500/15 text-green-700 dark:text-green-300",
  removed: "bg-red-500/15 text-red-700 dark:text-red-300",
  context: "text-muted-foreground",
};

function HunkView({ hunk }: { hunk: DiffHunk }) {
  let oldNo = hunk.oldStart;
  let newNo = hunk.newStart;
  return (
    <div className="font-mono text-xs">
      <div className="bg-muted px-2 py-0.5 text-muted-foreground">
        @@ -{hunk.oldStart},{hunk.oldLines} +{hunk.newStart},{hunk.newLines} @@
      </div>
      {hunk.segments.map((seg, i) => {
        const oldLabel = seg.type === "added" ? "" : String(oldNo++);
        const newLabel = seg.type === "removed" ? "" : String(newNo++);
        return (
          <div
            key={i}
            className={cn("flex whitespace-pre-wrap", ROW_CLASS[seg.type])}
            data-type={seg.type}
          >
            <span className="w-8 shrink-0 select-none text-right text-muted-foreground/60">
              {oldLabel}
            </span>
            <span className="w-8 shrink-0 select-none text-right text-muted-foreground/60">
              {newLabel}
            </span>
            <span className="w-4 shrink-0 select-none text-center" aria-hidden="true">
              {MARKER[seg.type]}
            </span>
            <span className="min-w-0 flex-1">{seg.value.replace(/\n$/, "")}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Detail header for the selected version: shows its label badges (spec 38 §5.3.4). */
function DetailHeader({ version, labels }: { version: number | null; labels: LabelBrief[] }) {
  const { t } = useTranslation("history");
  if (version === null || labels.length === 0) return null;
  return (
    <div
      className="flex flex-wrap items-center gap-1 border-b p-2"
      aria-label={t("diff.labelsForVersion", { version })}
    >
      {labels.map((label) => (
        <Badge key={label.id} variant="secondary">
          {label.name}
        </Badge>
      ))}
    </div>
  );
}

export function HistoryDiffView({
  projectId,
  docId,
  from,
  to,
  selectedVersion = null,
  selectedLabels = [],
}: {
  projectId: string;
  docId: string;
  from: number | null;
  to: number | "current" | null;
  selectedVersion?: number | null;
  selectedLabels?: LabelBrief[];
}) {
  const { t } = useTranslation("history");
  const query = useDiff(projectId, docId, from, to);
  const header = <DetailHeader version={selectedVersion} labels={selectedLabels} />;

  const body = (() => {
    if (from === null) {
      return (
        <p className="p-4 text-sm text-muted-foreground">{t("diff.selectPrompt")}</p>
      );
    }
    if (query.isLoading) {
      return (
        <div className="space-y-2 p-4" aria-busy="true">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-4" />
          ))}
        </div>
      );
    }
    if (query.isError || !query.data) {
      return (
        <div className="flex items-center gap-2 p-4 text-sm text-destructive" role="alert">
          {t("diff.loadFailed")}
          <Button size="sm" variant="outline" onClick={() => void query.refetch()}>
            {t("common:action.retry")}
          </Button>
        </div>
      );
    }

    const diff = query.data;
    if (diff.binary) {
      return <p className="p-4 text-sm text-muted-foreground">{t("diff.binary")}</p>;
    }
    if (diff.tooLarge) {
      return (
        <p className="p-4 text-sm text-muted-foreground">{t("diff.tooLarge")}</p>
      );
    }
    if (diff.hunks.length === 0) {
      return (
        <p className="p-4 text-sm text-muted-foreground">{t("diff.noChanges")}</p>
      );
    }

    return (
      <div className="space-y-3 p-2" role="region" aria-label={t("diff.ariaLabel")}>
        {diff.hunks.map((hunk, i) => (
          <HunkView key={i} hunk={hunk} />
        ))}
      </div>
    );
  })();

  return (
    <>
      {header}
      {body}
    </>
  );
}
