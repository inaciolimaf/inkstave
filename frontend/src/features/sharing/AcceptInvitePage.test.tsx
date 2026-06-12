import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { AcceptInvitePage } from "./AcceptInvitePage";
import type { InvitePreview } from "./types";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const navigate = vi.hoisted(() => vi.fn());
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigate, useParams: () => ({ token: "tok-123" }) };
});

const api = vi.hoisted(() => ({
  getInvitePreview: vi.fn(),
  acceptInvite: vi.fn(),
  declineInvite: vi.fn(),
}));
vi.mock("./api", () => ({
  getInvitePreview: (...a: unknown[]) => api.getInvitePreview(...a),
  acceptInvite: (...a: unknown[]) => api.acceptInvite(...a),
  declineInvite: (...a: unknown[]) => api.declineInvite(...a),
}));

const PREVIEW: InvitePreview = {
  projectId: "p1",
  projectName: "Paper",
  inviterName: "Owner",
  role: "editor",
  email: "bob@x.com",
};

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.clearAllMocks());

describe("AcceptInvitePage", () => {
  it("renders the invite preview", async () => {
    api.getInvitePreview.mockResolvedValue(PREVIEW);
    renderWithProviders(<AcceptInvitePage />, { route: "/invite/tok-123" });
    expect(await screen.findByText("You’re invited to Paper")).toBeInTheDocument();
    expect(screen.getByText(/Owner invited you/)).toBeInTheDocument();
  });

  it("accepts and navigates into the project", async () => {
    api.getInvitePreview.mockResolvedValue(PREVIEW);
    api.acceptInvite.mockResolvedValue({ projectId: "p1", role: "editor" });
    renderWithProviders(<AcceptInvitePage />, { route: "/invite/tok-123" });
    await screen.findByText("You’re invited to Paper");
    await userEvent.click(screen.getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/projects/p1"));
  });

  it("declines and returns to projects", async () => {
    api.getInvitePreview.mockResolvedValue(PREVIEW);
    api.declineInvite.mockResolvedValue(undefined);
    renderWithProviders(<AcceptInvitePage />, { route: "/invite/tok-123" });
    await screen.findByText("You’re invited to Paper");
    await userEvent.click(screen.getByRole("button", { name: "Decline" }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/projects"));
  });

  it("shows a clear message for an expired (410) invite", async () => {
    const { ApiError } = await import("@/lib/api-client");
    api.getInvitePreview.mockRejectedValue(new ApiError(410, "This invite is no longer valid."));
    renderWithProviders(<AcceptInvitePage />, { route: "/invite/tok-123" });
    expect(await screen.findByText("Invitation unavailable")).toBeInTheDocument();
  });
});
