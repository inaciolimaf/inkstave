import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { ShareDialog } from "./ShareDialog";
import type { Invite, Member } from "./types";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const authUser = vi.hoisted(() => ({ value: { id: "owner-1", display_name: "Owner" } }));
vi.mock("@/auth/auth-context", () => ({ useAuth: () => ({ user: authUser.value }) }));

const api = vi.hoisted(() => ({
  listMembers: vi.fn(),
  listInvites: vi.fn(),
  createInvite: vi.fn(),
  changeMemberRole: vi.fn(),
  removeMember: vi.fn(),
  revokeInvite: vi.fn(),
  transferOwnership: vi.fn(),
}));
vi.mock("./api", () => ({
  listMembers: (...a: unknown[]) => api.listMembers(...a),
  listInvites: (...a: unknown[]) => api.listInvites(...a),
  createInvite: (...a: unknown[]) => api.createInvite(...a),
  changeMemberRole: (...a: unknown[]) => api.changeMemberRole(...a),
  removeMember: (...a: unknown[]) => api.removeMember(...a),
  revokeInvite: (...a: unknown[]) => api.revokeInvite(...a),
  transferOwnership: (...a: unknown[]) => api.transferOwnership(...a),
}));

const OWNER: Member = {
  userId: "owner-1",
  name: "Owner",
  email: "owner@x.com",
  role: "owner",
  status: "active",
};
const BOB: Member = {
  userId: "bob-1",
  name: "Bob",
  email: "bob@x.com",
  role: "editor",
  status: "active",
};
const INVITE: Invite = {
  id: "inv-1",
  email: "carol@x.com",
  role: "viewer",
  status: "pending",
  expiresAt: "2026-07-01T00:00:00Z",
  createdAt: "2026-06-10T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  authUser.value = { id: "owner-1", display_name: "Owner" };
  api.listMembers.mockResolvedValue([OWNER, BOB]);
  api.listInvites.mockResolvedValue([INVITE]);
});
afterEach(() => vi.clearAllMocks());

function open() {
  return renderWithProviders(<ShareDialog projectId="p1" open onOpenChange={() => {}} />);
}

describe("ShareDialog (owner)", () => {
  it("shows members, pending invites and the invite form (AC11)", async () => {
    open();
    expect(await screen.findByText("Bob")).toBeInTheDocument();
    expect(screen.getByLabelText("Invite by email")).toBeInTheDocument();
    expect(await screen.findByText("carol@x.com")).toBeInTheDocument();
  });

  it("validates the email before enabling Invite", async () => {
    open();
    await screen.findByText("Bob");
    const button = screen.getByRole("button", { name: "Invite" });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Invite by email"), "not-an-email");
    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(button).toBeDisabled();
  });

  it("sends an invite and toasts on success", async () => {
    api.createInvite.mockResolvedValue({ ...INVITE, token: "t" });
    open();
    await screen.findByText("Bob");
    await userEvent.type(screen.getByLabelText("Invite by email"), "new@x.com");
    await userEvent.click(screen.getByRole("button", { name: "Invite" }));
    await waitFor(() => expect(api.createInvite).toHaveBeenCalledWith("p1", "new@x.com", "editor"));
    expect(toast.success).toHaveBeenCalled();
  });

  it("shows an inline error when the invite is rejected", async () => {
    const { ApiError } = await import("@/lib/api-client");
    api.createInvite.mockRejectedValue(new ApiError(409, "Already a member."));
    open();
    await screen.findByText("Bob");
    await userEvent.type(screen.getByLabelText("Invite by email"), "bob@x.com");
    await userEvent.click(screen.getByRole("button", { name: "Invite" }));
    // Server invite errors surface inline under the field (role="alert"), not as a toast.
    expect(await screen.findByRole("alert")).toHaveTextContent("Already a member.");
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("confirms before removing a member (AC11)", async () => {
    api.removeMember.mockResolvedValue(undefined);
    open();
    await screen.findByText("Bob");
    await userEvent.click(screen.getByRole("button", { name: "Remove Bob" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Remove Bob?")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(api.removeMember).toHaveBeenCalledWith("p1", "bob-1"));
  });

  it("revokes a pending invite after confirmation", async () => {
    api.revokeInvite.mockResolvedValue(undefined);
    open();
    await userEvent.click(
      await screen.findByRole("button", { name: "Revoke invite for carol@x.com" }),
    );
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(api.revokeInvite).toHaveBeenCalledWith("p1", "inv-1"));
  });

  it("confirms before transferring ownership (AC11)", async () => {
    api.transferOwnership.mockResolvedValue(undefined);
    open();
    await screen.findByText("Bob");
    await userEvent.click(screen.getByRole("button", { name: "Transfer" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Make Bob the owner?")).toBeInTheDocument();
    expect(api.transferOwnership).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Transfer" }));
    await waitFor(() => expect(api.transferOwnership).toHaveBeenCalledWith("p1", "bob-1"));
  });
});

describe("ShareDialog (non-owner)", () => {
  beforeEach(() => {
    authUser.value = { id: "bob-1", display_name: "Bob" };
  });

  it("is read-only with a Leave action and no invite form (AC11)", async () => {
    open();
    expect(await screen.findByText("Owner")).toBeInTheDocument();
    expect(screen.queryByLabelText("Invite by email")).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove Owner" })).toBeNull();
    expect(screen.getByRole("button", { name: "Leave project" })).toBeInTheDocument();
    expect(api.listInvites).not.toHaveBeenCalled();
  });
});
