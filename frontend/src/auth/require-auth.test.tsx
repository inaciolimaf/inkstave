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

function renderAt(isAuthenticated: boolean, isBootstrapping = false) {
  authState.value = { isAuthenticated, isBootstrapping };
  return render(
    <MemoryRouter initialEntries={["/secret"]}>
      <Routes>
        <Route element={<RequireAuth />}>
          <Route path="/secret" element={<div>secret content</div>} />
        </Route>
        <Route path="/login" element={<div>login page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RequireAuth", () => {
  it("redirects to /login when unauthenticated", () => {
    renderAt(false);
    expect(screen.getByText("login page")).toBeInTheDocument();
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("renders the protected route when authenticated", () => {
    renderAt(true);
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  it("shows a loading state while bootstrapping", () => {
    renderAt(false, true);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(screen.queryByText("login page")).not.toBeInTheDocument();
  });
});
