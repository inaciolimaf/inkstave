/** The chat's messages: paging, live updates, optimistic sends and soft deletes (spec 117). */
import { type InfiniteData, type QueryClient, useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState } from "react";

import { type ChatMessage, type ChatMessagePage, deleteMessage, fetchMessagesPage, postMessage } from "./api";
import { useProjectEvents } from "./use-project-events";

export const messagesKey = (projectId: string) => ["discussion", "chat", projectId, "messages"] as const;

type Messages = InfiniteData<ChatMessagePage, string | undefined>;

/** A message the writer sent that the server has not confirmed yet. */
export interface PendingMessage {
  localId: string;
  body: string;
  failed: boolean;
}

/** Add a message at the newest end, unless it is already there (the send and the event both carry it). */
function withMessage(data: Messages | undefined, message: ChatMessage): Messages | undefined {
  if (!data || data.pages.some((page) => page.items.some((item) => item.id === message.id))) return data;
  const [first, ...rest] = data.pages;
  if (!first) return data;
  return { ...data, pages: [{ ...first, items: [message, ...first.items] }, ...rest] };
}

/** A deleted message keeps its place; its body goes. */
function withDeleted(data: Messages | undefined, messageId: string): Messages | undefined {
  if (!data) return data;
  const pages = data.pages.map((page) => ({
    ...page,
    items: page.items.map((item) => (item.id === messageId ? { ...item, body: null, deleted: true } : item)),
  }));
  return { ...data, pages };
}

function updateMessages(
  queryClient: QueryClient,
  projectId: string,
  update: (data: Messages | undefined) => Messages | undefined,
): void {
  queryClient.setQueryData<Messages>(messagesKey(projectId), update);
}

export function useChat(projectId: string) {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingMessage[]>([]);
  const sequence = useRef(0);
  const { data, hasNextPage, isFetchingNextPage, fetchNextPage, isPending, isError } = useInfiniteQuery({
    queryKey: messagesKey(projectId),
    queryFn: ({ pageParam }) => fetchMessagesPage(projectId, pageParam),
    initialPageParam: undefined as string | undefined,
    // Pages arrive newest first; the next one starts before the oldest message shown so far.
    getNextPageParam: (last) =>
      last.has_more && last.items.length > 0 ? last.items[last.items.length - 1].id : undefined,
  });

  // Oldest first, the order a conversation reads in.
  const messages = useMemo(() => (data?.pages ?? []).flatMap((page) => page.items).reverse(), [data]);

  useProjectEvents(projectId, {
    onEvent: (event) => {
      if (event.type === "chat.message_created") {
        const message = event.payload as ChatMessage;
        updateMessages(queryClient, projectId, (d) => withMessage(d, message));
      } else if (event.type === "chat.message_deleted") {
        const { id } = event.payload as { id: string };
        updateMessages(queryClient, projectId, (d) => withDeleted(d, id));
      }
    },
    // After a (re)connect, events may have been missed: refetch what is shown.
    onOpen: () => void queryClient.invalidateQueries({ queryKey: messagesKey(projectId) }),
  });

  const attempt = useCallback(
    async (item: PendingMessage) => {
      try {
        const created = await postMessage(projectId, item.body);
        updateMessages(queryClient, projectId, (d) => withMessage(d, created));
        setPending((list) => list.filter((p) => p.localId !== item.localId));
      } catch {
        setPending((list) => list.map((p) => (p.localId === item.localId ? { ...p, failed: true } : p)));
      }
    },
    [projectId, queryClient],
  );

  const send = useCallback(
    (body: string) => {
      const text = body.trim();
      if (!text) return;
      sequence.current += 1;
      const item: PendingMessage = { localId: `local-${sequence.current}`, body: text, failed: false };
      setPending((list) => [...list, item]);
      void attempt(item);
    },
    [attempt],
  );

  const retry = useCallback(
    (item: PendingMessage) => {
      setPending((list) => list.map((p) => (p.localId === item.localId ? { ...p, failed: false } : p)));
      void attempt(item);
    },
    [attempt],
  );

  const remove = useCallback(
    async (messageId: string) => {
      try {
        await deleteMessage(projectId, messageId);
        updateMessages(queryClient, projectId, (d) => withDeleted(d, messageId));
      } catch {
        // Nothing changed on the server, so the list on screen is still right.
      }
    },
    [projectId, queryClient],
  );

  const loadOlder = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage]);

  return {
    messages,
    pending,
    send,
    retry,
    remove,
    loadOlder,
    hasOlder: Boolean(hasNextPage),
    loadingOlder: isFetchingNextPage,
    loading: isPending,
    failed: isError,
  };
}
