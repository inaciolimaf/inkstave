/** Project chat API calls (spec 117). The wire shapes come from the generated OpenAPI types. */
import type { Schemas } from "@/api/models";
import { apiClient } from "@/lib/api-client";

export type ChatMessage = Schemas["ChatMessageRead"];
export type ChatMessagePage = Schemas["ChatMessagePage"];

const base = (projectId: string) => `/api/v1/projects/${projectId}/chat`;

/** One page, newest first. `before` is the id of the oldest message already shown. */
export function fetchMessagesPage(projectId: string, before?: string): Promise<ChatMessagePage> {
  const query = before ? `?before=${encodeURIComponent(before)}` : "";
  return apiClient.get<ChatMessagePage>(`${base(projectId)}/messages${query}`);
}

export function postMessage(projectId: string, body: string): Promise<ChatMessage> {
  return apiClient.post<ChatMessage>(`${base(projectId)}/messages`, { body });
}

export async function deleteMessage(projectId: string, messageId: string): Promise<void> {
  await apiClient.delete(`${base(projectId)}/messages/${messageId}`);
}

export async function fetchUnreadCount(projectId: string): Promise<number> {
  return (await apiClient.get<Schemas["UnreadCount"]>(`${base(projectId)}/unread`)).count;
}

export async function markChatRead(projectId: string): Promise<void> {
  await apiClient.post(`${base(projectId)}/read`, {});
}
