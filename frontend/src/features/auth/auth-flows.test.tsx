import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/auth/auth-context";
import { tokenStore } from "@/lib/token-store";

import { ForgotPasswordPage } from "./ForgotPasswordPage";
import { MagicLinkPage } from "./MagicLinkPage";
import { ResetPasswordPage } from "./ResetPasswordPage";
import { VerifyEmailPage } from "./VerifyEmailPage";

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
  email_confirmed: true,
  created_at: "2026-01-01T00:00:00Z",
};
const PAIR = { access_token: "AT", refresh_token: "RT", token_type: "bearer", expires_in: 900 };

function renderAt(entry: string, element: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <AuthProvider>
        <Routes>
          <Route path="/verify-email" element={element} />
          <Route path="/magic-link" element={element} />
          <Route path="/reset-password" element={element} />
          <Route path="/forgot-password" element={element} />
          <Route path="/login" element={<div>login page</div>} />
          <Route path="/projects" element={<div>projects page</div>} />
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

describe("VerifyEmailPage", () => {
  it("POSTs the token exactly once on mount and shows success", async () => {
    const fetchMock = vi.fn(async () => mockResponse(200, USER));
    vi.stubGlobal("fetch", fetchMock);
    renderAt("/verify-email?token=tok", <VerifyEmailPage />);
    expect(await screen.findByText("Your email is verified. You’re all set.")).toBeInTheDocument();
    // The single-use token is POSTed exactly once (the `ran` ref guards re-runs).
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows the expired state on 410", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockResponse(410, { error: { message: "expired" } })),
    );
    renderAt("/verify-email?token=tok", <VerifyEmailPage />);
    expect(await screen.findByText(/this verification link has expired/i)).toBeInTheDocument();
  });

  it("shows the invalid state on 400", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockResponse(400, { error: { message: "invalid" } })),
    );
    renderAt("/verify-email?token=tok", <VerifyEmailPage />);
    expect(await screen.findByText(/invalid or has already been used/i)).toBeInTheDocument();
  });
});

describe("MagicLinkPage callback", () => {
  it("stores the pair and navigates to /projects on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.endsWith("/auth/magic-link/callback")
          ? mockResponse(200, PAIR)
          : mockResponse(200, USER),
      ),
    );
    renderAt("/magic-link?token=tok", <MagicLinkPage />);
    expect(await screen.findByText("projects page")).toBeInTheDocument();
    expect(tokenStore.getAccessToken()).toBe("AT");
  });

  it("offers a new link when the token is invalid", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockResponse(400, { error: { message: "invalid" } })),
    );
    renderAt("/magic-link?token=tok", <MagicLinkPage />);
    expect(await screen.findByRole("link", { name: /request a new link/i })).toBeInTheDocument();
  });
});

describe("ForgotPasswordPage (non-enumerating)", () => {
  it("shows the same success copy regardless of the response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockResponse(202, { detail: "ok" })),
    );
    const user = userEvent.setup();
    renderAt("/forgot-password", <ForgotPasswordPage />);
    await user.type(screen.getByLabelText("Email"), "ghost@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));
    expect(
      await screen.findByText(/if that email is registered, a reset link is on its way/i),
    ).toBeInTheDocument();
  });
});

describe("MagicLinkPage request (non-enumerating)", () => {
  it("shows the same success copy after requesting a link", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockResponse(202, { detail: "ok" })),
    );
    const user = userEvent.setup();
    renderAt("/magic-link", <MagicLinkPage />);
    await user.type(screen.getByLabelText("Email"), "anyone@example.com");
    await user.click(screen.getByRole("button", { name: /email me a link/i }));
    expect(await screen.findByText(/check your inbox for a sign-in link/i)).toBeInTheDocument();
  });
});

describe("ResetPasswordPage", () => {
  it("blocks a weak password with the shared schema (no request sent)", async () => {
    const fetchMock = vi.fn(async () => mockResponse(200, { detail: "ok" }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt("/reset-password?token=tok", <ResetPasswordPage />);
    await user.type(screen.getByLabelText("New password"), "short");
    await user.type(screen.getByLabelText("Confirm new password"), "short");
    await user.click(screen.getByRole("button", { name: /update password/i }));
    expect(await screen.findByText(/at least 8 characters/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits a valid password and shows success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockResponse(200, { detail: "Password updated — please sign in." })),
    );
    const user = userEvent.setup();
    renderAt("/reset-password?token=tok", <ResetPasswordPage />);
    await user.type(screen.getByLabelText("New password"), "Br4ndNewPass");
    await user.type(screen.getByLabelText("Confirm new password"), "Br4ndNewPass");
    await user.click(screen.getByRole("button", { name: /update password/i }));
    expect(await screen.findByText(/password updated — please sign in/i)).toBeInTheDocument();
  });

  it("shows the expired state on a 410", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockResponse(410, { error: { message: "expired" } })),
    );
    const user = userEvent.setup();
    renderAt("/reset-password?token=tok", <ResetPasswordPage />);
    await user.type(screen.getByLabelText("New password"), "Br4ndNewPass");
    await user.type(screen.getByLabelText("Confirm new password"), "Br4ndNewPass");
    await user.click(screen.getByRole("button", { name: /update password/i }));
    expect(await screen.findByText(/this reset link has expired/i)).toBeInTheDocument();
  });
});
