/** Strings for the notifications bell (the `notifications` namespace, spec 39). */
const dict = {
  title: "Notifications",
  unreadAria: "Notifications, {{count}} unread",
  markAllRead: "Mark all read",
  markRead: "Mark read",
  notification: "Notification",
  dismiss: "Dismiss notification",
  accept: "Accept",
  empty: "You’re all caught up.",
  loadFailed: "Couldn’t load notifications.",
  invite: {
    prefix: "{{inviter}} invited you to ",
    suffix: " as {{role}}",
    defaultInviter: "Someone",
    defaultProject: "a project",
    defaultRole: "collaborator",
  },
  fallbackMessage: "You have a new notification.",
};

export default dict;
export type Dict = typeof dict;
