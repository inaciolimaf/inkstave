import { AlertTriangle, Check, CloudOff, Loader2 } from "lucide-react";

import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import type { SaveStatus } from "./autosave/types";

const CONFIG: Record<
  SaveStatus,
  { label: string; variant: BadgeProps["variant"]; icon?: React.ReactNode }
> = {
  clean: { label: "Saved", variant: "muted", icon: <Check className="size-3" /> },
  dirty: { label: "Unsaved changes", variant: "outline" },
  saving: { label: "Saving…", variant: "muted", icon: <Loader2 className="size-3 animate-spin" /> },
  error: {
    label: "Save failed — retrying",
    variant: "destructive",
    icon: <AlertTriangle className="size-3" />,
  },
  offline: {
    label: "Offline — changes will save when you reconnect",
    variant: "destructive",
    icon: <CloudOff className="size-3" />,
  },
  conflict: {
    label: "Conflict",
    variant: "destructive",
    icon: <AlertTriangle className="size-3" />,
  },
};

/** A short relative phrase for the moment the document was last saved. */
function relativeSavedLabel(lastSavedAt: number): string {
  const seconds = Math.max(0, Math.round((Date.now() - lastSavedAt) / 1000));
  if (seconds < 5) return "Saved just now";
  if (seconds < 60) return `Saved ${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `Saved ${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  return `Saved ${hours}h ago`;
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
  const { variant, icon } = CONFIG[status];
  const label =
    status === "clean" && lastSavedAt != null
      ? relativeSavedLabel(lastSavedAt)
      : CONFIG[status].label;
  return (
    <div aria-live="polite" className="flex items-center gap-1" data-testid="save-status">
      <Badge variant={variant}>
        {icon}
        {label}
      </Badge>
      {status === "error" && (
        <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}
