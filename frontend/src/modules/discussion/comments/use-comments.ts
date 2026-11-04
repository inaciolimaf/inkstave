/**
 * The project's comment threads, kept current by the project event stream (spec 118), and the writes
 * that change them. Every write refetches the list, so the author sees the result even if the event
 * was lost; every `comment.*` event refetches it for the other members.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import {
  createThread,
  deleteMessage,
  editMessage,
  fetchThreads,
  type NewThread,
  replyToThread,
  setThreadResolved,
} from "./api";
import { useProjectEvents } from "../use-project-events";

export const commentsKey = (projectId: string) => ["discussion", "comments", projectId] as const;

export function useCommentThreads(projectId: string) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: commentsKey(projectId),
    queryFn: () => fetchThreads(projectId),
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
