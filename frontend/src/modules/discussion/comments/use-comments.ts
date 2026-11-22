/**
 * The project's comment threads, kept current by the project event stream (spec 118), and the writes
 * that change them. Every write refetches the list, so the author sees the result even if the event
 * was lost; every `comment.*` event refetches it for the other members.
 */
import { type InfiniteData, useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import {
  type CommentThread,
  createThread,
  deleteMessage,
  editMessage,
  fetchThreadPage,
  type NewThread,
  replyToThread,
  setThreadResolved,
  type ThreadPage,
} from "./api";
import { useProjectEvents } from "../use-project-events";

export const commentsKey = (projectId: string) => ["discussion", "comments", projectId] as const;

/** The loaded pages as one list, in page order. A stable reference, so the query does not re-select. */
const allThreads = (data: InfiniteData<ThreadPage>): CommentThread[] =>
  data.pages.flatMap((page) => page.items);

/**
 * The project's threads, loaded a page at a time: `data` is every loaded thread, and `fetchNextPage`
 * loads the next page on demand. A comment event refetches the loaded pages.
 */
export function useCommentThreads(projectId: string) {
  const queryClient = useQueryClient();
  const query = useInfiniteQuery({
    queryKey: commentsKey(projectId),
    queryFn: ({ pageParam }) => fetchThreadPage(projectId, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    select: allThreads,
  });
  const refresh = useCallback(
    () => void queryClient.invalidateQueries({ queryKey: commentsKey(projectId) }),
    [projectId, queryClient],
  );
  useProjectEvents(projectId, {
    onEvent: (event) => {
      if (event.type.startsWith("comment.")) refresh();
    },
    onOpen: refresh,
  });
  return query;
}

export interface ReplyInput {
  threadId: string;
  body: string;
  mentions: string[];
}

export interface EditInput extends ReplyInput {
  messageId: string;
}

export function useCommentMutations(projectId: string) {
  const { t } = useTranslation("discussion");
  const queryClient = useQueryClient();
  const settle = () => queryClient.invalidateQueries({ queryKey: commentsKey(projectId) });
  const onError = () => toast.error(t("comments.error.save"));

  const create = useMutation({
    mutationFn: (thread: NewThread) => createThread(projectId, thread),
    onSuccess: settle,
    onError,
  });
  const reply = useMutation({
    mutationFn: (input: ReplyInput) => replyToThread(projectId, input.threadId, input.body, input.mentions),
    onSuccess: settle,
    onError,
  });
  const edit = useMutation({
    mutationFn: (input: EditInput) =>
      editMessage(projectId, input.threadId, input.messageId, input.body, input.mentions),
    onSuccess: settle,
    onError,
  });
  const remove = useMutation({
    mutationFn: (input: { threadId: string; messageId: string }) =>
      deleteMessage(projectId, input.threadId, input.messageId),
    onSuccess: settle,
    onError,
  });
  const resolve = useMutation({
    mutationFn: (input: { threadId: string; resolved: boolean }) =>
      setThreadResolved(projectId, input.threadId, input.resolved),
    onSuccess: settle,
    onError,
  });
  return { create, reply, edit, remove, resolve };
}
