/** Strings for the project chat (the `discussion` namespace, spec 117). */
const dict = {
  title: "Project chat",
  tabs: {
    chat: "Chat",
  },
  button: {
    label: "Chat",
    unreadAria: "Chat, {{count}} unread",
  },
  empty: "No messages yet. Say hello to your collaborators.",
  loadOlder: "Load older messages",
  loading: "Loading the chat…",
  loadFailed: "Couldn’t load the chat.",
  composer: {
    label: "Message",
    placeholder: "Write a message…",
    send: "Send",
  },
  message: {
    you: "You",
    unknownAuthor: "Former member",
    deleted: "Message deleted",
    delete: "Delete message",
    sending: "Sending…",
    failed: "Not sent.",
    retry: "Retry",
  },
};

export default dict;
export type Dict = typeof dict;
