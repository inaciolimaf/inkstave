import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import type { CollabStatus } from "./useCollabDoc";

const STATUS_META: Record<CollabStatus, { labelKey: string; className: string }> = {
  connected: {
    labelKey: "collab.connected",
    className: "text-success-text",
  },
  connecting: {
    labelKey: "collab.connecting",
    className: "text-warning-text",
  },
  reconnecting: {
    labelKey: "collab.reconnecting",
    className: "text-warning-text",
  },
  offline: { labelKey: "collab.offline", className: "text-muted-foreground" },
};

/** Live-connection indicator for the editor toolbar (spec 31; presence is spec 32). */
export function ConnectionStatusBadge({ status }: { status: CollabStatus }) {
  const { t } = useTranslation("editor");
  const meta = STATUS_META[status];
  const label = t(meta.labelKey);
  return (
    <span
      aria-live="polite"
      aria-label={t("collab.connection", { status: label })}
      className={cn("inline-flex items-center gap-1.5 text-small font-medium", meta.className)}
    >
      <span className="size-2 rounded-full bg-current" aria-hidden="true" />
      {label}
    </span>
  );
}
