import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/auth/auth-context";
import { tokenStore } from "@/lib/token-store";

import { LoginPage } from "./login";
import { RegisterPage } from "./register";

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

function renderRegister() {
  return render(
    <MemoryRouter initialEntries={["/register"]}>
      <AuthProvider>
        <Routes>
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/login" element={<div>login page</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function fillValid(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Display name"), "Alice");
  await user.type(screen.getByLabelText("Email"), "alice@example.com");
  await user.type(screen.getByLabelText("Password"), "secret123");
  await user.type(screen.getByLabelText("Confirm password"), "secret123");
}

beforeEach(() => {
  tokenStore.clear();
  localStorage.clear();
});

afterEach(() => vi.unstubAllGlobals());

function renderRegisterWithLogin() {
  return render(
    <MemoryRouter initialEntries={["/register"]}>
      <AuthProvider>
        <Routes>
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/login" element={<LoginPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("RegisterPage", () => {
  it("registers, redirects to /login, and shows the success message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        mockResponse(201, {
          id: "u1",
          email: "alice@example.com",
          display_name: "Alice",
        }),
      ),
    );
    const user = userEvent.setup();
    renderRegisterWithLogin();
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));
    // Navigated to /login (the real LoginPage renders) with the justRegistered state.
    expect(await screen.findByText("Account created — please sign in.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("blocks submission and shows an error when passwords do not match", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderRegister();
    await user.type(screen.getByLabelText("Display name"), "Alice");
    await user.type(screen.getByLabelText("Email"), "alice@example.com");
    await user.type(screen.getByLabelText("Password"), "secret123");
    await user.type(screen.getByLabelText("Confirm password"), "different1");
    await user.click(screen.getByRole("button", { name: /create account/i }));
    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a non-field alert on a duplicate email (409)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockResponse(409, { error: { type: "conflict", message: "dup" } })),
    );
    const user = userEvent.setup();
    renderRegister();
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));
    expect(
      await screen.findByText("An account with this email already exists."),
    ).toBeInTheDocument();
  });

  it("maps a backend 422 to an inline field error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        mockResponse(422, {
          error: {
            type: "validation_error",
            message: "Request validation failed",
            details: [
              {
                loc: ["body", "password"],
                msg: "Password must not contain your email address.",
                type: "value_error",
              },
            ],
          },
        }),
      ),
    );
    const user = userEvent.setup();
    renderRegister();
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));
    expect(
      await screen.findByText("Password must not contain your email address."),
    ).toBeInTheDocument();
  });
});
