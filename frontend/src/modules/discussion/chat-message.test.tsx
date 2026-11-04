import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import type { ChatMessage as Message } from "./api";
import { ChatMessage } from "./chat-message";

function message(over: Partial<Message> = {}): Message {
  return {
    id: "m1",
    body: "hello",
    author: { id: "ana", display_name: "Ana" },
    created_at: "2026-11-04T10:00:00Z",
    deleted: false,
    ...over,
  };
}

function renderMessage(item: Message, own: boolean, onDelete = vi.fn()) {
  return renderWithProviders(
    <ul>
      <ChatMessage message={item} own={own} onDelete={onDelete} />
    </ul>,
  );
}

describe("ChatMessage", () => {
  it("renders Markdown, with links that open in a new tab", () => {
    renderMessage(message({ body: "**bold** and [a site](https://example.com)" }), false);
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    const link = screen.getByRole("link", { name: "a site" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("never renders raw HTML from a message", () => {
    const { container } = renderMessage(
      message({
        body: '<script>window.chatPwned = 1</script>\n\nsafe words <img src="x" onerror="window.chatPwned = 1"> after',
      }),
      false,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container).toHaveTextContent("safe words");
    expect(container).toHaveTextContent("after");
  });

  it("shows a deleted message as deleted, without its text", () => {
    renderMessage(message({ body: null, deleted: true }), false);
    expect(screen.getByText("Message deleted")).toBeInTheDocument();
  });

  it("puts own messages on the right with a delete button, and others' without one", async () => {
    const onDelete = vi.fn();
    const user = userEvent.setup();
    const { unmount } = renderMessage(message(), true, onDelete);
    expect(screen.getByRole("listitem")).toHaveAttribute("data-own", "true");
    await user.click(screen.getByRole("button", { name: "Delete message" }));
    expect(onDelete).toHaveBeenCalledWith("m1");
    unmount();

    renderMessage(message(), false, onDelete);
    expect(screen.getByRole("listitem")).toHaveAttribute("data-own", "false");
    expect(screen.queryByRole("button", { name: "Delete message" })).not.toBeInTheDocument();
  });

  it("names a message whose author has left", () => {
    renderMessage(message({ author: null }), false);
    expect(screen.getByText("Former member")).toBeInTheDocument();
  });
});
