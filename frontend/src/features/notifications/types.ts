/** Notification domain types mirroring the spec-39 API. */

export interface AppNotification {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  readAt: string | null;
  expiresAt: string | null;
  createdAt: string;
}

export interface NotificationList {
  items: AppNotification[];
  unreadCount: number;
}
