import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installFakeEventSource, latestEventSource } from "@/test/fake-event-source";
import { renderWithProviders } from "@/test/utils";

import type { ChatMessage as Message } from "./api";
import { ChatPanel } from "./chat-panel";

const api = vi.hoisted(() => ({
  fetchMessagesPage: vi.fn(),
  postMessage: vi.fn(),
  deleteMessage: vi.fn(),
  fetchUnreadCount: vi.fn(),
  markChatRead: vi.fn(),
}));
vi.mock("./api", () => api);
vi.mock("@/modules/auth/auth-context", () => ({
  useAuth: () => ({ user: { id: "me", display_name: "Me" } }),
}));

function message(id: string, body: string, authorId = "ana", name = "Ana"): Message {
  return {
    id,
    body,
    author: { id: authorId, display_name: name },
    created_at: "2026-11-04T10:00:00Z",
    deleted: false,
  };
}

const composer = () => screen.getByRole("textbox", { name: "Message" });

beforeEach(() => {
  installFakeEventSource();
  api.fetchMessagesPage.mockResolvedValue({ items: [], has_more: false });
  api.fetchUnreadCount.mockResolvedValue(0);
  api.markChatRead.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("ChatPanel", () => {
  it("shows an empty chat with a composer", async () => {
    renderWithProviders(<ChatPanel projectId="p1" active={false} />);
    expect(await screen.findByText(/No messages yet/)).toBeInTheDocument();
    expect(composer()).toBeInTheDocument();
  });

  it("sends a message and shows it", async () => {
    const user = userEvent.setup();
    api.postMessage.mockResolvedValue(message("m1", "Oi", "me", "Me"));
    renderWithProviders(<ChatPanel projectId="p1" active={false} />);

    await user.type(composer(), "Oi");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(api.postMessage).toHaveBeenCalledWith("p1", "Oi");
    await waitFor(() => expect(screen.getAllByText("Oi")).toHaveLength(1));
    expect(composer()).toHaveValue("");
  });

  it("keeps a message that failed to send, and sends it again on Retry", async () => {
    const user = userEvent.setup();
    api.postMessage
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(message("m1", "Oi", "me", "Me"));
    renderWithProviders(<ChatPanel projectId="p1" active={false} />);

    await user.type(composer(), "Oi");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Not sent.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByText("Not sent.")).not.toBeInTheDocument());
    expect(api.postMessage).toHaveBeenCalledTimes(2);
    expect(api.postMessage).toHaveBeenLastCalledWith("p1", "Oi");
    expect(screen.getAllByText("Oi")).toHaveLength(1);
  });

  it("loads older messages on request, without duplicates, oldest first", async () => {
    const user = userEvent.setup();
    api.fetchMessagesPage
      .mockResolvedValueOnce({ items: [message("m3", "third"), message("m2", "second")], has_more: true })
      .mockResolvedValueOnce({ items: [message("m1", "first")], has_more: false });
    renderWithProviders(<ChatPanel projectId="p1" active={false} />);

    expect(await screen.findByText("third")).toBeInTheDocument();
    const rows = within(screen.getByRole("log")).getAllByRole("listitem");
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("second"),
      expect.stringContaining("third"),
    ]);

    await user.click(screen.getByRole("button", { name: "Load older messages" }));
    expect(await screen.findByText("first")).toBeInTheDocument();
    expect(api.fetchMessagesPage).toHaveBeenLastCalledWith("p1", "m2");
    expect(screen.getAllByText(/^(first|second|third)$/)).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Load older messages" })).not.toBeInTheDocument();
  });

  it("shows a message posted by someone else as it arrives, and a deletion live", async () => {
    api.fetchMessagesPage.mockResolvedValue({
      items: [message("m1", "old note", "bruno", "Bruno")],
      has_more: false,
    });
    renderWithProviders(<ChatPanel projectId="p1" active={false} />);
    await screen.findByText("old note");
    const source = latestEventSource();

    act(() => {
      source.emit("chat.message_created", {
        id: 9,
        type: "chat.message_created",
        payload: message("m2", "hello live", "bruno", "Bruno"),
      });
    });
    expect(await screen.findByText("hello live")).toBeInTheDocument();

    act(() => {
      source.emit("chat.message_deleted", { id: 10, type: "chat.message_deleted", payload: { id: "m2" } });
    });
    expect(await screen.findByText("Message deleted")).toBeInTheDocument();
    expect(screen.queryByText("hello live")).not.toBeInTheDocument();
  });

  it("deletes an own message and shows it as deleted", async () => {
    const user = userEvent.setup();
    api.fetchMessagesPage.mockResolvedValue({ items: [message("m1", "mine", "me", "Me")], has_more: false });
    api.deleteMessage.mockResolvedValue(undefined);
    renderWithProviders(<ChatPanel projectId="p1" active={false} />);

    await user.click(await screen.findByRole("button", { name: "Delete message" }));
    expect(api.deleteMessage).toHaveBeenCalledWith("p1", "m1");
    expect(await screen.findByText("Message deleted")).toBeInTheDocument();
  });

  it("marks the chat read when it is the visible view, and again as messages arrive", async () => {
    const { rerender } = renderWithProviders(<ChatPanel projectId="p1" active={false} />);
    await screen.findByText(/No messages yet/);
    expect(api.markChatRead).not.toHaveBeenCalled();

    rerender(<ChatPanel projectId="p1" active />);
    await waitFor(() => expect(api.markChatRead).toHaveBeenCalledWith("p1"));

    api.markChatRead.mockClear();
    act(() => {
      latestEventSource().emit("chat.message_created", {
        id: 4,
        type: "chat.message_created",
        payload: message("m5", "new one", "bruno", "Bruno"),
      });
    });
    await waitFor(() => expect(api.markChatRead).toHaveBeenCalledTimes(1));
  });
});
