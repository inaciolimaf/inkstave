/** React Query hooks for the notifications bell (spec 39). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { config } from "@/config";

import {
  dismissNotification,
  fetchUnreadCount,
  listNotifications,
  markAllRead,
  markRead,
} from "./api";
import type { NotificationList } from "./types";

const UNREAD_KEY = ["notifications", "unread-count"] as const;
const LIST_KEY = ["notifications", "list"] as const;

export function useUnreadCount() {
  return useQuery({
    queryKey: UNREAD_KEY,
    queryFn: fetchUnreadCount,
    refetchInterval: config.notificationsPollIntervalMs,
  });
}

export function useNotifications(enabled: boolean) {
  return useQuery({ queryKey: LIST_KEY, queryFn: listNotifications, enabled });
}

export function useNotificationMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: LIST_KEY });
    void qc.invalidateQueries({ queryKey: UNREAD_KEY });
  };

  const read = useMutation({ mutationFn: markRead, onSuccess: invalidate });
  const readAll = useMutation({ mutationFn: markAllRead, onSuccess: invalidate });
  const dismiss = useMutation({
    mutationFn: dismissNotification,
    // True optimistic update (spec 39 §5.3): remove the item from the cache
    // immediately, then roll back to the snapshot if the DELETE fails.
    onMutate: async (id: string) => {
      await qc.cancelQueries({ queryKey: LIST_KEY });
      const previous = qc.getQueryData<NotificationList>(LIST_KEY);
      if (previous) {
        qc.setQueryData<NotificationList>(LIST_KEY, {
          ...previous,
          items: previous.items.filter((n) => n.id !== id),
        });
      }
      return { previous };
    },
    onError: (_err, _id, context) => {
      if (context?.previous) qc.setQueryData(LIST_KEY, context.previous);
    },
    onSettled: invalidate, // reconcile with server truth in both paths
  });

  return { read, readAll, dismiss };
}
