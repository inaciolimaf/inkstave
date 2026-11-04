/** Comment thread API calls (spec 118). The wire shapes come from the generated OpenAPI types. */
import type { Schemas } from "@/api/models";
import { apiClient } from "@/lib/api-client";

export type CommentThread = Schemas["CommentThreadRead"];
export type CommentMessage = Schemas["CommentMessageRead"];

const base = (projectId: string) => `/api/v1/projects/${projectId}/comments`;

export interface NewThread {
  documentId: string;
  anchorStart: string;
  anchorEnd: string;
  quotedText: string;
  body: string;
  mentions: string[];
}

export async function fetchThreads(projectId: string): Promise<CommentThread[]> {
  return (await apiClient.get<Schemas["CommentThreadList"]>(`${base(projectId)}?status=all`)).items;
}

export function createThread(projectId: string, thread: NewThread): Promise<CommentThread> {
  return apiClient.post<CommentThread>(base(projectId), {
    document_id: thread.documentId,
    anchor_start: thread.anchorStart,
    anchor_end: thread.anchorEnd,
    quoted_text: thread.quotedText,
    body: thread.body,
    mentions: thread.mentions,
  });
}

export function replyToThread(
  projectId: string,
  threadId: string,
  body: string,
  mentions: string[],
): Promise<CommentMessage> {
  return apiClient.post<CommentMessage>(`${base(projectId)}/${threadId}/messages`, { body, mentions });
}

export function editMessage(
  projectId: string,
  threadId: string,
  messageId: string,
  body: string,
  mentions: string[],
): Promise<CommentMessage> {
  return apiClient.patch<CommentMessage>(`${base(projectId)}/${threadId}/messages/${messageId}`, {
    body,
    mentions,
  });
}

export async function deleteMessage(projectId: string, threadId: string, messageId: string): Promise<void> {
  await apiClient.delete(`${base(projectId)}/${threadId}/messages/${messageId}`);
}

export function setThreadResolved(
  projectId: string,
  threadId: string,
  resolved: boolean,
): Promise<CommentThread> {
  const action = resolved ? "resolve" : "reopen";
  return apiClient.post<CommentThread>(`${base(projectId)}/${threadId}/${action}`, {});
}
