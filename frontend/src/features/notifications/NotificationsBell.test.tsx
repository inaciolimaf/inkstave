import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { NotificationsBell } from "./NotificationsBell";
import type { AppNotification } from "./types";

const navigate = vi.hoisted(() => vi.fn());
vi.mock("react-router-dom", async (orig) => ({
  ...(await orig<typeof import("react-router-dom")>()),
  useNavigate: () => navigate,
}));

const api = vi.hoisted(() => ({
  listNotifications: vi.fn(),
  fetchUnreadCount: vi.fn(),
  markRead: vi.fn(),
  markAllRead: vi.fn(),
  dismissNotification: vi.fn(),
}));
vi.mock("./api", () => api);

afterEach(() => vi.clearAllMocks());

function invite(over: Partial<AppNotification> = {}): AppNotification {
  return {
    id: "n1",
    type: "project_invite",
    payload: {
      inviter_name: "Ada",
      project_name: "Paper",
      role: "editor",
      invite_id: "i1",
      accept_url: "http://localhost/invite/tok123",
    },
    readAt: null,
    expiresAt: null,
    createdAt: new Date(Date.now() - 3600_000).toISOString(),
    ...over,
  };
}

describe("NotificationsBell", () => {
  it("shows the unread badge count (criterion 11)", async () => {
    api.fetchUnreadCount.mockResolvedValue(3);
    api.listNotifications.mockResolvedValue({ items: [], unreadCount: 3 });
    renderWithProviders(<NotificationsBell />);
    expect(await screen.findByText("3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /3 unread/ })).toBeInTheDocument();
  });

  it("lists notifications and renders the invite message", async () => {
    api.fetchUnreadCount.mockResolvedValue(1);
    api.listNotifications.mockResolvedValue({ items: [invite()], unreadCount: 1 });
    renderWithProviders(<NotificationsBell />);
    await userEvent.click(await screen.findByRole("button", { name: /Notifications/ }));
    expect(await screen.findByText(/invited you to/)).toBeInTheDocument();
    expect(screen.getByText("Paper")).toBeInTheDocument();
  });

  it("marks read and dismisses via the API (criterion 11)", async () => {
    api.fetchUnreadCount.mockResolvedValue(1);
    api.listNotifications.mockResolvedValue({ items: [invite()], unreadCount: 1 });
    api.markRead.mockResolvedValue(undefined);
    api.dismissNotification.mockResolvedValue(undefined);
    renderWithProviders(<NotificationsBell />);
    await userEvent.click(await screen.findByRole("button", { name: /Notifications/ }));

    await userEvent.click(await screen.findByLabelText("Mark read"));
    await waitFor(() => expect(api.markRead.mock.calls[0]?.[0]).toBe("n1"));

    await userEvent.click(screen.getByLabelText("Dismiss notification"));
    await waitFor(() => expect(api.dismissNotification.mock.calls[0]?.[0]).toBe("n1"));
  });

  it("Accept navigates to the invite acceptance route (criterion 11)", async () => {
    api.fetchUnreadCount.mockResolvedValue(1);
    api.listNotifications.mockResolvedValue({ items: [invite()], unreadCount: 1 });
    renderWithProviders(<NotificationsBell />);
    await userEvent.click(await screen.findByRole("button", { name: /Notifications/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Accept" }));
    expect(navigate).toHaveBeenCalledWith("/invite/tok123");
  });

  it("shows the loading skeleton while the list is pending (criterion 157a)", async () => {
    api.fetchUnreadCount.mockResolvedValue(0);
    api.listNotifications.mockReturnValue(new Promise(() => {})); // never resolves
    renderWithProviders(<NotificationsBell />);
    await userEvent.click(await screen.findByRole("button", { name: /Notifications/ }));
    await waitFor(() =>
      expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument(),
    );
  });

  it("shows the error + retry UI when the list fails (criterion 157b)", async () => {
    api.fetchUnreadCount.mockResolvedValue(0);
    api.listNotifications.mockRejectedValue(new Error("boom"));
    renderWithProviders(<NotificationsBell />);
    await userEvent.click(await screen.findByRole("button", { name: /Notifications/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Couldn’t load notifications/);

    // Retry refetches the list (now succeeds → list renders).
    api.listNotifications.mockResolvedValue({ items: [invite()], unreadCount: 1 });
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/invited you to/)).toBeInTheDocument();
  });

  it("rolls the dismissed item back when DELETE fails (criteria 157c + 162)", async () => {
    api.fetchUnreadCount.mockResolvedValue(1);
    api.listNotifications.mockResolvedValue({ items: [invite()], unreadCount: 1 });
    // Dismiss rejects; the optimistic removal must be rolled back.
    api.dismissNotification.mockRejectedValue(new Error("nope"));
    renderWithProviders(<NotificationsBell />);
    await userEvent.click(await screen.findByRole("button", { name: /Notifications/ }));
    expect(await screen.findByText(/invited you to/)).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("Dismiss notification"));
    await waitFor(() => expect(api.dismissNotification.mock.calls[0]?.[0]).toBe("n1"));

    // After the rejection + onSettled invalidate (server still has the item),
    // the notification reappears (rollback succeeded).
    expect(await screen.findByText(/invited you to/)).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    api.fetchUnreadCount.mockResolvedValue(0);
    api.listNotifications.mockResolvedValue({ items: [], unreadCount: 0 });
    renderWithProviders(<NotificationsBell />);
    await userEvent.click(await screen.findByRole("button", { name: /Notifications/ }));
    expect(await screen.findByText("You’re all caught up.")).toBeInTheDocument();
  });
});
