import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SetupPage } from "./setup-page";

const api = vi.hoisted(() => ({
  getSetupStatus: vi.fn(),
  createFirstAdmin: vi.fn(),
}));
vi.mock("@/features/setup/api", () => api);

afterEach(() => vi.clearAllMocks());

function renderSetup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/setup"]}>
        <Routes>
          <Route path="/setup" element={<SetupPage />} />
          <Route path="/login" element={<div>login page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SetupPage", () => {
  it("shows the admin-creation form when setup is needed (AC5)", async () => {
    api.getSetupStatus.mockResolvedValue({ needsSetup: true });
    renderSetup();
    expect(await screen.findByText("Set up Inkstave")).toBeInTheDocument();
    expect(screen.getByLabelText("Display name")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create admin/i })).toBeInTheDocument();
  });

  it("redirects to /login when setup is already done (AC6)", async () => {
    api.getSetupStatus.mockResolvedValue({ needsSetup: false });
    renderSetup();
    expect(await screen.findByText("login page")).toBeInTheDocument();
    expect(screen.queryByText("Set up Inkstave")).not.toBeInTheDocument();
  });

  it("posts the admin and routes to /login on success (AC7)", async () => {
    api.getSetupStatus.mockResolvedValue({ needsSetup: true });
    api.createFirstAdmin.mockResolvedValue(undefined);
    renderSetup();
    await screen.findByText("Set up Inkstave");

    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Display name"), "Admin");
    await user.type(screen.getByLabelText("Email"), "admin@example.com");
    await user.type(screen.getByLabelText("Password"), "Str0ng-Passw0rd!");
    await user.click(screen.getByRole("button", { name: /create admin/i }));

    await waitFor(() =>
      expect(api.createFirstAdmin).toHaveBeenCalledWith({
        email: "admin@example.com",
        password: "Str0ng-Passw0rd!",
        displayName: "Admin",
      }),
    );
    expect(await screen.findByText("login page")).toBeInTheDocument();
  });
});
