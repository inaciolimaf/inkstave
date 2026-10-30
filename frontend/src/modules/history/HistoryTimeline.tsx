/** Reverse-chronological versions list with pagination + selection (spec 38). */
import { useTranslation } from "react-i18next";

import { QueryView } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { HistoryLabels } from "./HistoryLabels";
import { absoluteTime, relativeTime } from "./format";
import type { Version } from "./types";
import { useVersions } from "./useHistory";

interface RowProps {
  version: Version;
  selected: boolean;
  compared: boolean;
  canWrite: boolean;
  onSelect: (version: number, extend: boolean) => void;
  onAddLabel: (version: number, name: string) => void;
  onDeleteLabel: (labelId: string) => void;
}

function VersionRow({
  version,
  selected,
  compared,
  canWrite,
  onSelect,
  onAddLabel,
  onDeleteLabel,
}: RowProps) {
  const { t } = useTranslation("history");
  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected || compared}
      onClick={(e) => onSelect(version.version, e.shiftKey)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(version.version, e.shiftKey);
        }
      }}
      className={cn(
        "cursor-pointer border-l-2 border-transparent py-2 pl-2 pr-1 text-body focus-visible:-outline-offset-2",
        selected && "border-foreground",
        compared && !selected && "border-dashed border-foreground",
      )}
    >
      <div className="flex items-center gap-2">
        <span className="mr-auto truncate font-medium">
          {version.author?.name ?? t("timeline.unknownAuthor")}
        </span>
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="whitespace-nowrap text-small tabular-nums text-muted-foreground">
                {relativeTime(version.timestamp)}
              </span>
            </TooltipTrigger>
            <TooltipContent>{absoluteTime(version.timestamp)}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="text-small tabular-nums text-muted-foreground">
          v{version.version} · {t("timeline.changes", { count: version.opCount })}
        </span>
        <HistoryLabels
          version={version.version}
          labels={version.labels}
          canWrite={canWrite}
          onAdd={onAddLabel}
          onDelete={onDeleteLabel}
        />
      </div>
    </div>
  );
}

export function HistoryTimeline({
  projectId,
  docId,
  primary,
  compare,
  canWrite,
  onSelect,
  onAddLabel,
  onDeleteLabel,
}: {
  projectId: string;
  docId: string;
  primary: number | null;
  compare: number | null;
  canWrite: boolean;
  onSelect: (version: number, extend: boolean) => void;
  onAddLabel: (version: number, name: string) => void;
  onDeleteLabel: (labelId: string) => void;
}) {
  const { t } = useTranslation("history");
  const query = useVersions(projectId, docId, true);

  const loading = (
    <div className="space-y-2" aria-busy="true">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-12" />
      ))}
    </div>
  );

  return (
    <QueryView query={query} loading={loading} errorMessage={t("timeline.loadFailed")}>
      {(data) => {
        const versions = data.pages.flatMap((page) => page.versions);
        if (versions.length === 0) {
          return <p className="text-body text-muted-foreground">{t("timeline.empty")}</p>;
        }
        return (
          <div className="divide-y divide-border" role="list" aria-label={t("timeline.ariaLabel")}>
            {versions.map((version) => (
              <div role="listitem" key={version.version}>
                <VersionRow
                  version={version}
                  selected={primary === version.version}
                  compared={compare === version.version}
                  canWrite={canWrite}
                  onSelect={onSelect}
                  onAddLabel={onAddLabel}
                  onDeleteLabel={onDeleteLabel}
                />
              </div>
            ))}
            {query.hasNextPage && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                disabled={query.isFetchingNextPage}
                onClick={() => void query.fetchNextPage()}
              >
                {query.isFetchingNextPage ? t("timeline.loading") : t("timeline.loadMore")}
              </Button>
            )}
          </div>
        );
      }}
    </QueryView>
  );
}
