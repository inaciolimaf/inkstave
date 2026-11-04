import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { GitAccessSection } from "./GitAccessSection";

const api = vi.hoisted(() => ({
  listGitTokens: vi.fn(),
  createGitToken: vi.fn(),
  revokeGitToken: vi.fn(),
}));
vi.mock("./git-api", () => api);

const existing = {
  id: "t1",
  name: "Laptop",
  prefix: "ink_abcdef12",
  created_at: "2026-01-01T00:00:00Z",
  last_used_at: null,
  expires_at: null,
};

describe("GitAccessSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listGitTokens.mockResolvedValue({ tokens: [existing] });
  });

  it("lists the tokens with their prefix and never-used state", async () => {
    renderWithProviders(<GitAccessSection />, { route: "/settings" });
    expect(await screen.findByText("Laptop")).toBeInTheDocument();
    expect(screen.getByText("Starts with ink_abcdef12…", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("never used", { exact: false })).toBeInTheDocument();
  });

  it("shows a new token once, with a copy button", async () => {
    api.createGitToken.mockResolvedValue({ ...existing, id: "t2", name: "Desk", token: "ink_secret-value" });
    renderWithProviders(<GitAccessSection />, { route: "/settings" });
    await screen.findByText("Laptop");
    await userEvent.type(screen.getByLabelText("Name"), "Desk");
    await userEvent.click(screen.getByRole("button", { name: "Create token" }));
    expect(await screen.findByText("ink_secret-value")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
    expect(api.createGitToken).toHaveBeenCalledWith({ name: "Desk", expires_at: null });
  });

  it("revokes a token after confirmation", async () => {
    api.revokeGitToken.mockResolvedValue(undefined);
    renderWithProviders(<GitAccessSection />, { route: "/settings" });
    await screen.findByText("Laptop");
    await userEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await userEvent.click(await screen.findByRole("button", { name: "Revoke token" }));
    await waitFor(() => expect(api.revokeGitToken).toHaveBeenCalledWith("t1"));
  });
});
