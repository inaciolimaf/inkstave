import { AlertTriangle, Check, CloudOff, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import type { SaveStatus } from "./autosave/types";

const CONFIG: Record<
  SaveStatus,
  { labelKey: string; variant: BadgeProps["variant"]; icon?: React.ReactNode }
> = {
  clean: { labelKey: "saveStatus.saved", variant: "muted", icon: <Check className="size-3" /> },
  dirty: { labelKey: "saveStatus.unsaved", variant: "outline" },
  saving: {
    labelKey: "saveStatus.saving",
    variant: "muted",
    icon: <Loader2 className="size-3 animate-spin" />,
  },
  error: {
    labelKey: "saveStatus.saveFailed",
    variant: "destructive",
    icon: <AlertTriangle className="size-3" />,
  },
  offline: {
    labelKey: "saveStatus.offline",
    variant: "destructive",
    icon: <CloudOff className="size-3" />,
  },
  conflict: {
    labelKey: "saveStatus.conflict",
    variant: "destructive",
    icon: <AlertTriangle className="size-3" />,
  },
};

/** A short relative phrase for the moment the document was last saved. */
function relativeSavedLabel(lastSavedAt: number, t: TFunction<"editor">): string {
  const seconds = Math.max(0, Math.round((Date.now() - lastSavedAt) / 1000));
  if (seconds < 5) return t("saveStatus.savedJustNow");
  if (seconds < 60) return t("saveStatus.savedSecondsAgo", { seconds });
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return t("saveStatus.savedMinutesAgo", { minutes });
  const hours = Math.round(minutes / 60);
  return t("saveStatus.savedHoursAgo", { hours });
}

export function SaveStatusIndicator({
  status,
  onRetry,
  lastSavedAt = null,
}: {
  status: SaveStatus;
  onRetry: () => void;
  lastSavedAt?: number | null;
}) {
  const { t } = useTranslation("editor");
  const { variant, icon } = CONFIG[status];
  const label =
    status === "clean" && lastSavedAt != null
      ? relativeSavedLabel(lastSavedAt, t)
      : t(CONFIG[status].labelKey);
  return (
    <div aria-live="polite" className="flex items-center gap-1" data-testid="save-status">
      <Badge variant={variant}>
        {icon}
        {label}
      </Badge>
      {status === "error" && (
        <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={onRetry}>
          {t("saveStatus.retry")}
        </Button>
      )}
    </div>
  );
}
