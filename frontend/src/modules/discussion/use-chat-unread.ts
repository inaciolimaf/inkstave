/** The chat's unread count, kept current by the project event stream (spec 117). */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { fetchUnreadCount, markChatRead } from "./api";
import { useProjectEvents } from "./use-project-events";

export const unreadKey = (projectId: string) => ["discussion", "chat", projectId, "unread"] as const;

export function useChatUnread(projectId: string) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: unreadKey(projectId),
    queryFn: () => fetchUnreadCount(projectId),
  });

  const refresh = useCallback(
    () => void queryClient.invalidateQueries({ queryKey: unreadKey(projectId) }),
    [projectId, queryClient],
  );

  useProjectEvents(projectId, {
    onEvent: (event) => {
      if (event.type.startsWith("chat.")) refresh();
    },
    onOpen: refresh,
  });

  /** Opening the chat reads it. A failed call leaves the badge up until the next open. */
  const markRead = useCallback(async () => {
    try {
      await markChatRead(projectId);
    } catch {
      return;
    }
    await queryClient.invalidateQueries({ queryKey: unreadKey(projectId) });
  }, [projectId, queryClient]);

  return { count: query.data ?? 0, markRead };
}
