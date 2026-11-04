import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { alreadyHasAccess } from "./access";
import { JoinLinkPage } from "./JoinLinkPage";
import type { SharePreview } from "./types";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const navigate = vi.hoisted(() => vi.fn());
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigate, useParams: () => ({ token: "tok-123" }) };
});

const api = vi.hoisted(() => ({
  getSharePreview: vi.fn(),
  joinShareLink: vi.fn(),
}));
vi.mock("./api", () => ({
  getSharePreview: (...a: unknown[]) => api.getSharePreview(...a),
  joinShareLink: (...a: unknown[]) => api.joinShareLink(...a),
}));

const PREVIEW: SharePreview = {
  projectId: "p1",
  projectName: "Paper",
  ownerName: "Owner",
  role: "editor",
  alreadyMemberRole: null,
};

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.clearAllMocks());

describe("JoinLinkPage", () => {
  it("shows the project, its owner and the role the link grants", async () => {
    api.getSharePreview.mockResolvedValue(PREVIEW);
    renderWithProviders(<JoinLinkPage />, { route: "/join/tok-123" });

    expect(await screen.findByText("Paper")).toBeInTheDocument();
    expect(screen.getByText(/Owner shared this project with you/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Join" })).toBeInTheDocument();
  });

  it("joins and navigates into the project", async () => {
    api.getSharePreview.mockResolvedValue(PREVIEW);
    api.joinShareLink.mockResolvedValue({ projectId: "p1", role: "editor" });
    renderWithProviders(<JoinLinkPage />, { route: "/join/tok-123" });

    await userEvent.click(await screen.findByRole("button", { name: "Join" }));

    await waitFor(() => expect(api.joinShareLink).toHaveBeenCalledWith("tok-123"));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/projects/p1"));
  });

  it("says so and offers Open when the caller already has equal or higher access", async () => {
    api.getSharePreview.mockResolvedValue({ ...PREVIEW, role: "viewer", alreadyMemberRole: "editor" });
    renderWithProviders(<JoinLinkPage />, { route: "/join/tok-123" });

    expect(await screen.findByText("You already have access")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Join" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(navigate).toHaveBeenCalledWith("/projects/p1");
    expect(api.joinShareLink).not.toHaveBeenCalled();
  });

  it("still offers Join to a viewer who opens the edit link (an upgrade)", async () => {
    api.getSharePreview.mockResolvedValue({ ...PREVIEW, alreadyMemberRole: "viewer" });
    renderWithProviders(<JoinLinkPage />, { route: "/join/tok-123" });

    expect(await screen.findByRole("button", { name: "Join" })).toBeInTheDocument();
    expect(screen.queryByText("You already have access")).toBeNull();
  });

  it("answers a revoked or unknown link with the no-longer-valid message", async () => {
    const { ApiError } = await import("@/lib/api-client");
    api.getSharePreview.mockRejectedValue(new ApiError(404, "This link is no longer valid."));
    renderWithProviders(<JoinLinkPage />, { route: "/join/tok-123" });

    expect(await screen.findByText("Link unavailable")).toBeInTheDocument();
    expect(screen.getByText("This link is no longer valid.")).toBeInTheDocument();
  });
});

describe("alreadyHasAccess", () => {
  it("is true only when the current role covers the link's role", () => {
    expect(alreadyHasAccess(null, "viewer")).toBe(false);
    expect(alreadyHasAccess("viewer", "editor")).toBe(false);
    expect(alreadyHasAccess("editor", "viewer")).toBe(true);
    expect(alreadyHasAccess("editor", "editor")).toBe(true);
    expect(alreadyHasAccess("owner", "editor")).toBe(true);
  });
});
