/** Top-bar notifications bell: unread badge, list, mark-read/dismiss/accept (spec 39). */
import { Bell, X } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import type { AppNotification } from "./types";
import { useNotificationMutations, useNotifications, useUnreadCount } from "./useNotifications";

function relativeTime(iso: string): string {
  const seconds = Math.round((new Date(iso).getTime() - Date.now()) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, secs] of units) {
    if (Math.abs(seconds) >= secs) return rtf.format(Math.round(seconds / secs), unit);
  }
  return rtf.format(Math.round(seconds), "second");
}

function describe(n: AppNotification): ReactNode {
  if (n.type === "project_invite") {
    const p = n.payload;
    return (
      <>
        {String(p.inviter_name ?? "Someone")} invited you to{" "}
        <strong>{String(p.project_name ?? "a project")}</strong> as{" "}
        {String(p.role ?? "collaborator")}
      </>
    );
  }
  return String(n.payload.message ?? "You have a new notification.");
}

function NotificationRow({
  notification,
  onRead,
  onDismiss,
  onAccept,
}: {
  notification: AppNotification;
  onRead: (id: string) => void;
  onDismiss: (id: string) => void;
  onAccept: (n: AppNotification) => void;
}) {
  const unread = notification.readAt === null;
  return (
    <div
      role="listitem"
      className={cn("flex gap-2 rounded-md p-2 text-sm", unread && "bg-primary/5")}
    >
      <button
        type="button"
        className="min-w-0 flex-1 text-left"
        aria-label={unread ? "Mark read" : "Notification"}
        onClick={() => unread && onRead(notification.id)}
      >
        <span className="block break-words">{describe(notification)}</span>
        <span className="mt-0.5 block text-xs text-muted-foreground">
          {relativeTime(notification.createdAt)}
        </span>
      </button>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <button
          type="button"
          aria-label="Dismiss notification"
          className="text-muted-foreground hover:text-destructive"
          onClick={() => onDismiss(notification.id)}
        >
          <X className="size-4" />
        </button>
        {notification.type === "project_invite" && (
          <Button
            size="sm"
            variant="outline"
            className="mt-1 h-7"
            onClick={() => onAccept(notification)}
          >
            Accept
          </Button>
        )}
      </div>
    </div>
  );
}

export function NotificationsBell() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const unread = useUnreadCount();
  const list = useNotifications(open);
  const { read, readAll, dismiss } = useNotificationMutations();

  const count = unread.data ?? 0;

  const onAccept = (n: AppNotification) => {
    const acceptUrl = n.payload.accept_url;
    if (typeof acceptUrl === "string") {
      try {
        navigate(new URL(acceptUrl).pathname);
      } catch {
        navigate(acceptUrl);
      }
    }
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={`Notifications${count > 0 ? `, ${count} unread` : ""}`}
        >
          <Bell className="size-5" />
          {count > 0 && (
            <Badge
              className="absolute -right-1 -top-1 flex size-5 items-center justify-center p-0 text-xs"
              variant="destructive"
            >
              {count > 9 ? "9+" : count}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-2">
        <div className="mb-1 flex items-center justify-between px-1">
          <span className="text-sm font-medium">Notifications</span>
          {count > 0 && (
            <Button
              size="sm"
              variant="ghost"
              className="h-6 text-xs"
              onClick={() => readAll.mutate()}
            >
              Mark all read
            </Button>
          )}
        </div>
        {list.isLoading ? (
          <div className="space-y-2" aria-busy="true">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : list.isError ? (
          <div
            className="flex items-center justify-between p-2 text-sm text-destructive"
            role="alert"
          >
            Couldn’t load notifications.
            <Button size="sm" variant="outline" onClick={() => void list.refetch()}>
              Retry
            </Button>
          </div>
        ) : (list.data?.items.length ?? 0) === 0 ? (
          <p className="p-4 text-center text-sm text-muted-foreground">You’re all caught up.</p>
        ) : (
          <div className="max-h-96 space-y-1 overflow-auto" role="list" aria-label="Notifications">
            {list.data!.items.map((n) => (
              <NotificationRow
                key={n.id}
                notification={n}
                onRead={(id) => read.mutate(id)}
                onDismiss={(id) => dismiss.mutate(id)}
                onAccept={onAccept}
              />
            ))}
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
