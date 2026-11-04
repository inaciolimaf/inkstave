import { describe, expect, it } from "vitest";

import { commentLink, isCommentNotification } from "./comment-link";
import type { AppNotification } from "./types";

function row(type: string, payload: Record<string, unknown>): AppNotification {
  return { id: "n1", type, payload, readAt: null, expiresAt: null, createdAt: "2026-11-04T10:00:00Z" };
}

describe("comment notification rows", () => {
  it("recognises mentions and replies, and not invites", () => {
    expect(isCommentNotification(row("comment_mention", {}))).toBe(true);
    expect(isCommentNotification(row("comment_reply", {}))).toBe(true);
    expect(isCommentNotification(row("project_invite", {}))).toBe(false);
  });

  it("opens the project at the thread", () => {
    const link = commentLink(row("comment_reply", { project_id: "p1", thread_id: "t 1" }));
    expect(link).toBe("/projects/p1?thread=t%201");
  });

  it("has no link without both ids", () => {
    expect(commentLink(row("comment_mention", { project_id: "p1" }))).toBeNull();
  });
});
