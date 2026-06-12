/** The History side panel: timeline + diff + restore (spec 38). */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { hasCapability, usePermissions } from "@/features/sharing/usePermissions";

import { HistoryDiffView } from "./HistoryDiffView";
import { HistoryTimeline } from "./HistoryTimeline";
import { RestoreVersionButton } from "./RestoreVersionButton";
import { useHistoryMutations, useVersions } from "./useHistory";

export function HistoryPanel({
  projectId,
  docId,
  open,
  onOpenChange,
}: {
  projectId: string;
  docId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation("history");
  const perms = usePermissions(projectId);
  const canWrite = hasCapability(perms.data, "doc_write");
  const { addLabel, removeLabel, restore } = useHistoryMutations(projectId, docId);

  const [primary, setPrimary] = useState<number | null>(null);
  const [compare, setCompare] = useState<number | null>(null);
  useEffect(() => {
    setPrimary(null);
    setCompare(null);
  }, [docId]);

  const onSelect = (version: number, extend: boolean) => {
    if (extend && primary !== null && version !== primary) {
      setCompare(version);
    } else {
      setPrimary(version);
      setCompare(null);
    }
  };

  // The selected version's labels also appear as badges in the detail header (§5.3.4);
  // reuse the timeline's already-fetched versions cache rather than a second request.
  const versionsQuery = useVersions(projectId, docId, open);
  const selectedVersion =
    versionsQuery.data?.pages.flatMap((page) => page.versions).find((v) => v.version === primary) ??
    null;

  const from = compare !== null && primary !== null ? Math.min(primary, compare) : primary;
  const to: number | "current" | null =
    compare !== null && primary !== null
      ? Math.max(primary, compare)
      : primary !== null
        ? "current"
        : null;

  const onAddLabel = (version: number, name: string) =>
    addLabel.mutate({ version, name }, { onError: () => toast.error(t("toast.addLabelFailed")) });
  const onDeleteLabel = (labelId: string) =>
    removeLabel.mutate(labelId, { onError: () => toast.error(t("toast.removeLabelFailed")) });

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-4 sm:max-w-3xl">
        <SheetHeader>
          <SheetTitle>{t("panel.title")}</SheetTitle>
          <SheetDescription>{t("panel.description")}</SheetDescription>
        </SheetHeader>
        <div className="grid min-h-0 flex-1 grid-cols-2 gap-3">
          <div className="overflow-auto pr-1">
            <HistoryTimeline
              projectId={projectId}
              docId={docId}
              primary={primary}
              compare={compare}
              canWrite={canWrite}
              onSelect={onSelect}
              onAddLabel={onAddLabel}
              onDeleteLabel={onDeleteLabel}
            />
          </div>
          <div className="flex min-h-0 flex-col overflow-hidden rounded-md border">
            {canWrite && primary !== null && (
              <div className="border-b p-2">
                <RestoreVersionButton version={primary} restore={restore} />
              </div>
            )}
            <div className="min-h-0 flex-1 overflow-auto">
              <HistoryDiffView
                projectId={projectId}
                docId={docId}
                from={from}
                to={to}
                selectedVersion={primary}
                selectedLabels={selectedVersion?.labels ?? []}
              />
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
