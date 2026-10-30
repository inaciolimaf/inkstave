import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import type { UserPublic } from "@/types";

import { SettingsPage } from "./SettingsPage";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const auth = vi.hoisted(() => ({
  user: {
    id: "u1",
    email: "owner@example.com",
    display_name: "Owner",
    is_admin: false,
    email_confirmed: true,
    created_at: "2026-01-01T00:00:00Z",
    avatar_url: null,
    editor_preferences: { theme: "system", font_size: 14, keymap: "default" },
    pending_email: null,
  } as UserPublic,
  applyUser: vi.fn(),
  refreshUser: vi.fn(),
  logout: vi.fn(),
}));
vi.mock("@/auth/auth-context", () => ({ useAuth: () => auth }));

const api = vi.hoisted(() => ({
  updateProfile: vi.fn(),
  putEditorPreferences: vi.fn(),
  changePassword: vi.fn(),
  changeEmail: vi.fn(),
  deleteAccount: vi.fn(),
  confirmEmailChange: vi.fn(),
}));
vi.mock("./api", () => api);

describe("SettingsPage", () => {
  it("renders labeled forms for every section", () => {
    renderWithProviders(<SettingsPage />, { route: "/settings" });
    expect(screen.getByLabelText("Display name")).toBeInTheDocument();
    expect(screen.getByLabelText("Theme")).toBeInTheDocument();
    expect(screen.getByLabelText("Keymap")).toBeInTheDocument();
    expect(screen.getByLabelText("New email")).toBeInTheDocument();
    expect(screen.getByLabelText("New password")).toBeInTheDocument();
    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
  });

  it("saves the profile and surfaces success", async () => {
    api.updateProfile.mockResolvedValue({ ...auth.user, display_name: "Renamed" });
    renderWithProviders(<SettingsPage />, { route: "/settings" });

    const name = screen.getByLabelText("Display name");
    await userEvent.clear(name);
    await userEvent.type(name, "Renamed");
    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(api.updateProfile).toHaveBeenCalledWith({ display_name: "Renamed" }));
    expect(auth.applyUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalled();
  });

  it("blocks the password change until the confirmation matches", async () => {
    renderWithProviders(<SettingsPage />, { route: "/settings" });
    await userEvent.type(screen.getByLabelText("Current password"), "Sup3rPass");
    await userEvent.type(screen.getByLabelText("New password"), "FreshSecret9");
    await userEvent.type(screen.getByLabelText("Confirm new password"), "Mismatch9");

    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change password" })).toBeDisabled();
    expect(api.changePassword).not.toHaveBeenCalled();
  });
});
