import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import type { CollabStatus } from "./useCollabDoc";

const STATUS_META: Record<CollabStatus, { labelKey: string; className: string }> = {
  connected: {
    labelKey: "collab.connected",
    className: "border-green-500/30 text-green-600 dark:text-green-400",
  },
  connecting: {
    labelKey: "collab.connecting",
    className: "border-amber-500/30 text-amber-600 dark:text-amber-400",
  },
  reconnecting: {
    labelKey: "collab.reconnecting",
    className: "border-amber-500/30 text-amber-600 dark:text-amber-400",
  },
  offline: { labelKey: "collab.offline", className: "text-muted-foreground" },
};

/** Live-connection indicator for the editor toolbar (spec 31; presence is spec 32). */
export function ConnectionStatusBadge({ status }: { status: CollabStatus }) {
  const { t } = useTranslation("editor");
  const meta = STATUS_META[status];
  const label = t(meta.labelKey);
  return (
    <Badge
      variant="outline"
      aria-live="polite"
      aria-label={t("collab.connection", { status: label })}
      className={cn("gap-1.5", meta.className)}
    >
      <span className="size-2 rounded-full bg-current" aria-hidden="true" />
      {label}
    </Badge>
  );
}
