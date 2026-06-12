import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import type { CollabStatus } from "./useCollabDoc";

const STATUS_META: Record<CollabStatus, { label: string; className: string }> = {
  connected: { label: "Live", className: "border-green-500/30 text-green-600 dark:text-green-400" },
  connecting: {
    label: "Connecting…",
    className: "border-amber-500/30 text-amber-600 dark:text-amber-400",
  },
  reconnecting: {
    label: "Reconnecting…",
    className: "border-amber-500/30 text-amber-600 dark:text-amber-400",
  },
  offline: { label: "Offline", className: "text-muted-foreground" },
};

/** Live-connection indicator for the editor toolbar (spec 31; presence is spec 32). */
export function ConnectionStatusBadge({ status }: { status: CollabStatus }) {
  const meta = STATUS_META[status];
  return (
    <Badge
      variant="outline"
      aria-live="polite"
      aria-label={`Connection: ${meta.label}`}
      className={cn("gap-1.5", meta.className)}
    >
      <span className="size-2 rounded-full bg-current" aria-hidden="true" />
      {meta.label}
    </Badge>
  );
}
