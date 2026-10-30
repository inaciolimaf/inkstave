/** Notification API calls (spec 39). */
import type { Schemas } from "@/api/models";
import { apiClient } from "@/lib/api-client";

import type { AppNotification, NotificationList } from "./types";

const BASE = "/api/v1/notifications";

type WireNotification = Schemas["NotificationRead"];

function toNotification(w: WireNotification): AppNotification {
  return {
    id: w.id,
    type: w.type,
    payload: w.payload,
    readAt: w.read_at,
    expiresAt: w.expires_at,
    createdAt: w.created_at,
  };
}

export async function listNotifications(): Promise<NotificationList> {
  const wire = await apiClient.get<Schemas["NotificationList"]>(BASE);
  return { items: wire.items.map(toNotification), unreadCount: wire.unread_count };
}

export async function fetchUnreadCount(): Promise<number> {
  return (await apiClient.get<Schemas["UnreadCount"]>(`${BASE}/unread-count`)).count;
}

export async function markRead(id: string): Promise<void> {
  await apiClient.post(`${BASE}/${id}/read`, {});
}

export async function markAllRead(): Promise<number> {
  return (await apiClient.post<Schemas["MarkAllResult"]>(`${BASE}/read-all`, {})).updated;
}

export async function dismissNotification(id: string): Promise<void> {
  await apiClient.delete(`${BASE}/${id}`);
}
