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
    label: "Save failed",
    variant: "destructive",
    icon: <AlertTriangle className="size-3" />,
  },
  offline: { label: "Offline", variant: "destructive", icon: <CloudOff className="size-3" /> },
  conflict: {
    label: "Conflict",
    variant: "destructive",
    icon: <AlertTriangle className="size-3" />,
  },
};

export function SaveStatusIndicator({
  status,
  onRetry,
}: {
  status: SaveStatus;
  onRetry: () => void;
}) {
  const { label, variant, icon } = CONFIG[status];
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
