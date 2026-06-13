import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/auth/auth-context";
import { tokenStore } from "@/lib/token-store";

import { LoginPage } from "./login";

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

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/projects" element={<div>home page</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  tokenStore.clear();
  localStorage.clear();
});

afterEach(() => vi.unstubAllGlobals());

describe("LoginPage", () => {
  it("shows an error alert on invalid credentials (401)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.endsWith("/auth/login")
          ? mockResponse(401, { error: { message: "Invalid email or password." } })
          : mockResponse(200, {}),
      ),
    );
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.type(screen.getByLabelText("Password"), "secret123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText("Invalid email or password.")).toBeInTheDocument();
  });

  it("logs in and redirects home on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.endsWith("/auth/login") ? mockResponse(200, PAIR) : mockResponse(200, USER),
      ),
    );
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.type(screen.getByLabelText("Password"), "secret123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText("home page")).toBeInTheDocument();
  });

  it("disables the submit button while the request is pending", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/auth/login")) {
          await gate;
          return mockResponse(200, PAIR);
        }
        return mockResponse(200, USER);
      }),
    );
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.type(screen.getByLabelText("Password"), "secret123");
    const button = screen.getByRole("button", { name: /sign in/i });
    await user.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    release();
    // Let the resolved request settle (navigates home) to avoid act() warnings.
    expect(await screen.findByText("home page")).toBeInTheDocument();
  });
});
