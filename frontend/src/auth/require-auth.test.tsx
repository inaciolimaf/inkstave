import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { RequireAuth } from "./require-auth";

const authState = vi.hoisted(() => ({
  value: { isAuthenticated: false, isBootstrapping: false },
}));

vi.mock("@/auth/auth-context", () => ({
  useAuth: () => authState.value,
}));

const setup = vi.hoisted(() => ({ getSetupStatus: vi.fn() }));
vi.mock("@/features/setup/api", () => setup);

function renderAt(isAuthenticated: boolean, isBootstrapping = false) {
  authState.value = { isAuthenticated, isBootstrapping };
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/secret"]}>
        <Routes>
          <Route element={<RequireAuth />}>
            <Route path="/secret" element={<div>secret content</div>} />
          </Route>
          <Route path="/login" element={<div>login page</div>} />
          <Route path="/setup" element={<div>setup page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RequireAuth", () => {
  it("redirects to /login when unauthenticated and setup is done", async () => {
    setup.getSetupStatus.mockResolvedValue({ needsSetup: false });
    renderAt(false);
    expect(await screen.findByText("login page")).toBeInTheDocument();
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("redirects to /setup when unauthenticated and no admin exists yet (AC4)", async () => {
    setup.getSetupStatus.mockResolvedValue({ needsSetup: true });
    renderAt(false);
    expect(await screen.findByText("setup page")).toBeInTheDocument();
    expect(screen.queryByText("login page")).not.toBeInTheDocument();
  });

  it("renders the protected route when authenticated", () => {
    setup.getSetupStatus.mockResolvedValue({ needsSetup: false });
    renderAt(true);
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  it("shows a loading state while bootstrapping", () => {
    setup.getSetupStatus.mockResolvedValue({ needsSetup: false });
    renderAt(false, true);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(screen.queryByText("login page")).not.toBeInTheDocument();
  });
});
