import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "@/lib/token-store";

import { AuthProvider, useAuth } from "./auth-context";

function mockResponse(status: number, body?: unknown) {
  const text = body === undefined ? "" : JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => JSON.parse(text),
    text: async () => text,
  };
}

const USER = {
  id: "1",
  email: "a@b.com",
  display_name: "Alice",
  is_admin: false,
  email_confirmed: false,
  created_at: "2026-01-01T00:00:00Z",
};
const PAIR = { access_token: "AT", refresh_token: "RT", token_type: "bearer", expires_in: 900 };

function Harness() {
  const { isAuthenticated, logout } = useAuth();
  return (
    <div>
      <span data-testid="state">{isAuthenticated ? "in" : "out"}</span>
      <button onClick={() => void logout()}>logout</button>
    </div>
  );
}

beforeEach(() => {
  tokenStore.clear();
  localStorage.clear();
});

afterEach(() => vi.unstubAllGlobals());

describe("AuthProvider logout", () => {
  it("clears local state even when the logout network call fails", async () => {
    // Start authenticated via bootstrap (persisted refresh token).
    localStorage.setItem("inkstave.refresh_token", "RT");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/auth/refresh")) return mockResponse(200, PAIR);
        if (url.endsWith("/users/me")) return mockResponse(200, USER);
        if (url.endsWith("/auth/logout")) throw new Error("network down");
        return mockResponse(200, {});
      }),
    );

    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>,
    );

    expect(await screen.findByText("in")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "logout" }));

    expect(await screen.findByText("out")).toBeInTheDocument();
    expect(tokenStore.getAccessToken()).toBeNull();
    expect(tokenStore.getRefreshToken()).toBeNull();
  });
});
