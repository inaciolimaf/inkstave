/** Renders the spec-37 diff hunks with added/removed markers (spec 38). */
import { useTranslation } from "react-i18next";

import { QueryView } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import type { DiffHunk, LabelBrief, SegmentType } from "./types";
import { useDiff } from "./useHistory";

const MARKER: Record<SegmentType, string> = { added: "+", removed: "\u2212", context: " " };
const ROW_CLASS: Record<SegmentType, string> = {
  added: "bg-success-soft text-success-text",
  removed: "bg-error-soft text-error-text",
  context: "text-foreground",
};
const GUTTER_CLASS: Record<SegmentType, string> = {
  added: "",
  removed: "",
  context: "text-muted-foreground",
};

function HunkView({ hunk }: { hunk: DiffHunk }) {
  let oldNo = hunk.oldStart;
  let newNo = hunk.newStart;
  return (
    <div className="py-2 font-mono text-small">
      <div className="pb-1 text-muted-foreground">
        @@ -{hunk.oldStart},{hunk.oldLines} +{hunk.newStart},{hunk.newLines} @@
      </div>
      {hunk.segments.map((seg, i) => {
        const oldLabel = seg.type === "added" ? "" : String(oldNo++);
        const newLabel = seg.type === "removed" ? "" : String(newNo++);
        return (
          <div key={i} className={cn("flex whitespace-pre-wrap", ROW_CLASS[seg.type])} data-type={seg.type}>
            <span className={cn("w-8 shrink-0 select-none text-right", GUTTER_CLASS[seg.type])}>
              {oldLabel}
            </span>
            <span className={cn("w-8 shrink-0 select-none text-right", GUTTER_CLASS[seg.type])}>
              {newLabel}
            </span>
            <span className="w-4 shrink-0 select-none text-center" aria-hidden="true">
              {MARKER[seg.type]}
            </span>
            <span className="min-w-0 flex-1 break-words">{seg.value.replace(/\n$/, "")}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Detail header for the selected version: shows its labels (spec 38 §5.3.4). */
function DetailHeader({ version, labels }: { version: number | null; labels: LabelBrief[] }) {
  const { t } = useTranslation("history");
  if (version === null || labels.length === 0) return null;
  return (
    <div
      className="flex flex-wrap items-center gap-x-3 border-b border-border py-2 text-small"
      aria-label={t("diff.labelsForVersion", { version })}
    >
      {labels.map((label) => (
        <span key={label.id}>{label.name}</span>
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
      return <p className="py-4 text-body text-muted-foreground">{t("diff.selectPrompt")}</p>;
    }
    const loading = (
      <div className="space-y-2 py-4" aria-busy="true">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-4" />
        ))}
      </div>
    );
    return (
      <QueryView query={query} loading={loading} errorMessage={t("diff.loadFailed")} errorClassName="py-4">
        {(diff) => {
          if (diff.binary) {
            return <p className="py-4 text-body text-muted-foreground">{t("diff.binary")}</p>;
          }
          if (diff.tooLarge) {
            return <p className="py-4 text-body text-muted-foreground">{t("diff.tooLarge")}</p>;
          }
          if (diff.hunks.length === 0) {
            return <p className="py-4 text-body text-muted-foreground">{t("diff.noChanges")}</p>;
          }
          return (
            <div className="divide-y divide-border" role="region" aria-label={t("diff.ariaLabel")}>
              {diff.hunks.map((hunk, i) => (
                <HunkView key={i} hunk={hunk} />
              ))}
            </div>
          );
        }}
      </QueryView>
    );
  })();

  return (
    <>
      {header}
      {body}
    </>
  );
}
