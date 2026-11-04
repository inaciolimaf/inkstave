import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { ShareDialog } from "./ShareDialog";
import type { Member, ShareLink } from "./types";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const authUser = vi.hoisted(() => ({ value: { id: "owner-1", display_name: "Owner" } }));
vi.mock("@/modules/auth/auth-context", () => ({ useAuth: () => ({ user: authUser.value }) }));

const api = vi.hoisted(() => ({
  listMembers: vi.fn(),
  listInvites: vi.fn(),
  listShareLinks: vi.fn(),
  createShareLink: vi.fn(),
  revokeShareLink: vi.fn(),
}));
vi.mock("./api", () => ({
  listMembers: (...a: unknown[]) => api.listMembers(...a),
  listInvites: (...a: unknown[]) => api.listInvites(...a),
  listShareLinks: (...a: unknown[]) => api.listShareLinks(...a),
  createShareLink: (...a: unknown[]) => api.createShareLink(...a),
  revokeShareLink: (...a: unknown[]) => api.revokeShareLink(...a),
  createInvite: vi.fn(),
  changeMemberRole: vi.fn(),
  removeMember: vi.fn(),
  revokeInvite: vi.fn(),
  transferOwnership: vi.fn(),
}));

const OWNER: Member = {
  userId: "owner-1",
  name: "Owner",
  email: "owner@x.com",
  role: "owner",
  status: "active",
  viaLink: false,
};
const BOB: Member = {
  userId: "bob-1",
  name: "Bob",
  email: "bob@x.com",
  role: "editor",
  status: "active",
  viaLink: true,
};
const EDIT_LINK: ShareLink = { id: "link-1", role: "editor", createdAt: "2026-11-01T00:00:00Z" };

const writeText = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  authUser.value = { id: "owner-1", display_name: "Owner" };
  api.listMembers.mockResolvedValue([OWNER, BOB]);
  api.listInvites.mockResolvedValue([]);
  api.listShareLinks.mockResolvedValue([]);
  Object.assign(navigator, { clipboard: { writeText } });
  writeText.mockResolvedValue(undefined);
});
afterEach(() => vi.clearAllMocks());

function open() {
  return renderWithProviders(<ShareDialog projectId="p1" open onOpenChange={() => {}} />);
}

describe("Share with a link (owner)", () => {
  it("turning the edit link on creates it and offers Copy with the URL", async () => {
    const url = "http://localhost:5173/join/tok-edit";
    api.createShareLink.mockResolvedValue({ ...EDIT_LINK, token: "tok-edit", url });
    // The server lists the new link once it exists.
    api.listShareLinks.mockResolvedValueOnce([]).mockResolvedValue([EDIT_LINK]);
    open();
    await userEvent.click(await screen.findByRole("switch", { name: "Anyone with the link can edit" }));
    await waitFor(() => expect(api.createShareLink).toHaveBeenCalledWith("p1", "editor"));

    expect(await screen.findByRole("button", { name: "Copy" })).toBeInTheDocument();
    expect(screen.getByText("Link on")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(url));
    expect(toast.success).toHaveBeenCalledWith("Link copied.");
  });

  it("after a reload the row says Link on, explains the one-time view, and has no Copy", async () => {
    api.listShareLinks.mockResolvedValue([EDIT_LINK]);
    open();

    expect(await screen.findByText("Link on")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Anyone with the link can edit" })).toBeChecked();
    expect(
      screen.getByText("For safety the link is shown only once. Rotate to get a new one."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy" })).toBeNull();
  });

  it("turning the link off revokes it", async () => {
    api.listShareLinks.mockResolvedValue([EDIT_LINK]);
    api.revokeShareLink.mockResolvedValue(undefined);
    open();
    await userEvent.click(await screen.findByRole("switch", { name: "Anyone with the link can edit" }));

    await waitFor(() => expect(api.revokeShareLink).toHaveBeenCalledWith("p1", "link-1"));
  });

  it("rotating asks first, and only the confirmation creates the new link", async () => {
    api.listShareLinks.mockResolvedValue([EDIT_LINK]);
    api.createShareLink.mockResolvedValue({ ...EDIT_LINK, id: "link-2", token: "t2", url: "u2" });
    open();

    await userEvent.click(await screen.findByRole("button", { name: "Rotate the editor link" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Rotate the editor link?")).toBeInTheDocument();
    expect(api.createShareLink).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole("button", { name: "Rotate" }));
    await waitFor(() => expect(api.createShareLink).toHaveBeenCalledWith("p1", "editor"));
  });

  it("marks members who joined through a link", async () => {
    open();
    expect(await screen.findByText("via link")).toBeInTheDocument();
    expect(screen.getAllByText("via link")).toHaveLength(1);
  });
});

describe("Share with a link (non-owner)", () => {
  beforeEach(() => {
    authUser.value = { id: "bob-1", display_name: "Bob" };
  });

  it("does not show the section or fetch links", async () => {
    open();
    expect(await screen.findByText("Owner")).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "Anyone with the link can edit" })).toBeNull();
    expect(api.listShareLinks).not.toHaveBeenCalled();
  });
});
