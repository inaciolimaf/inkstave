/** Reverse-chronological versions list with pagination + selection (spec 38). */
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { HistoryLabels } from "./HistoryLabels";
import { absoluteTime, initials, relativeTime } from "./format";
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
        "cursor-pointer rounded-md border p-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring",
        selected && "border-primary bg-primary/5",
        compared && !selected && "border-primary/50 bg-primary/5",
      )}
    >
      <div className="flex items-center gap-2">
        <span
          className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium"
          aria-hidden="true"
        >
          {version.author ? initials(version.author.name) : "?"}
        </span>
        <span className="mr-auto truncate font-medium">
          {version.author?.name ?? t("timeline.unknownAuthor")}
        </span>
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="text-xs text-muted-foreground">
                {relativeTime(version.timestamp)}
              </span>
            </TooltipTrigger>
            <TooltipContent>{absoluteTime(version.timestamp)}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">
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

  if (query.isLoading) {
    return (
      <div className="space-y-2" aria-busy="true">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12" />
        ))}
      </div>
    );
  }
  if (query.isError) {
    return (
      <div className="flex items-center gap-2 text-sm text-destructive" role="alert">
        {t("timeline.loadFailed")}
        <Button size="sm" variant="outline" onClick={() => void query.refetch()}>
          {t("common:action.retry")}
        </Button>
      </div>
    );
  }

  const versions = (query.data?.pages ?? []).flatMap((page) => page.versions);
  if (versions.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("timeline.empty")}</p>;
  }

  return (
    <div className="space-y-2" role="list" aria-label={t("timeline.ariaLabel")}>
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
          variant="outline"
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
}
