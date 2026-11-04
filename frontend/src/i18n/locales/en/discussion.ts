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
  /** Comment threads on the text (spec 118). */
  comments: {
    title: "Comments",
    description: "Comment threads on the text of this project.",
    close: "Close comments",
    /** The review column's tabs: the comment threads and the suggested changes (spec 119). */
    tabs: {
      label: "Review",
      comments: "Comments",
      suggestions: "Suggestions",
    },
    button: {
      label: "Comments",
      openAria: "Comments, {{count}} open",
    },
    selection: {
      comment: "Comment",
    },
    filter: {
      label: "Filter comments",
      open: "Open",
      resolved: "Resolved",
      all: "All",
    },
    scope: {
      label: "Which comments",
      file: "This file",
      all: "All files",
    },
    empty: "No comments here.",
    thread: {
      label: "Comment thread",
      messages: "Messages",
    },
    detached: "Detached comment",
    detachedNotice: "The text this comment was on was removed",
    messageDeleted: "Message deleted",
    edited: "edited",
    formerMember: "Former member",
    you: "You",
    edit: "Edit",
    delete: "Delete",
    save: "Save",
    cancel: "Cancel",
    resolve: "Resolve",
    reopen: "Reopen",
    reply: {
      label: "Reply",
      placeholder: "Reply…",
      send: "Send",
    },
    composer: {
      label: "New comment",
      placeholder: "Add a comment on the selected text…",
      submit: "Comment",
    },
    mentions: {
      label: "Members",
      hint: "Type @ to mention a member. Ctrl/Cmd+Enter sends.",
    },
    error: {
      save: "Couldn’t save the comment. Try again.",
    },
  },
};

export default dict;
export type Dict = typeof dict;
