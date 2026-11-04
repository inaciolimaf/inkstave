/** The comment rows of the bell (spec 118): a mention, or a reply in a thread the user took part in. */
import type { AppNotification } from "./types";

export function isCommentNotification(n: AppNotification): boolean {
  return n.type === "comment_mention" || n.type === "comment_reply";
}

/** Where a comment row leads: the project, opened at its thread. */
export function commentLink(n: AppNotification): string | null {
  const projectId = n.payload.project_id;
  const threadId = n.payload.thread_id;
  if (typeof projectId !== "string" || typeof threadId !== "string") return null;
  return `/projects/${projectId}?thread=${encodeURIComponent(threadId)}`;
}
