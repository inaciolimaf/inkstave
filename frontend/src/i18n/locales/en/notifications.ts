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
  comment: {
    mention: "{{author}} mentioned you in a comment on {{project}}",
    reply: "{{author}} replied to a comment you took part in, on {{project}}",
    defaultAuthor: "Someone",
    defaultProject: "a project",
  },
  fallbackMessage: "You have a new notification.",
};

export default dict;
export type Dict = typeof dict;
