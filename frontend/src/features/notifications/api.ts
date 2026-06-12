/** Notification API calls (spec 39). */
import { apiClient } from "@/lib/api-client";

import type { AppNotification, NotificationList } from "./types";

const BASE = "/api/v1/notifications";

interface WireNotification {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  read_at: string | null;
  expires_at: string | null;
  created_at: string;
}

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
  const wire = await apiClient.get<{ items: WireNotification[]; unread_count: number }>(BASE);
  return { items: wire.items.map(toNotification), unreadCount: wire.unread_count };
}

export async function fetchUnreadCount(): Promise<number> {
  return (await apiClient.get<{ count: number }>(`${BASE}/unread-count`)).count;
}

export async function markRead(id: string): Promise<void> {
  await apiClient.post(`${BASE}/${id}/read`, {});
}

export async function markAllRead(): Promise<number> {
  return (await apiClient.post<{ updated: number }>(`${BASE}/read-all`, {})).updated;
}

export async function dismissNotification(id: string): Promise<void> {
  await apiClient.delete(`${BASE}/${id}`);
}
