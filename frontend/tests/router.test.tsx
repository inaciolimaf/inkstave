import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "@/lib/token-store";

import { FAKE_USER, fakeApi, renderScreen } from "./helpers/screen";

const SESSION = {
  "POST /auth/refresh": { access_token: "a", refresh_token: "r", token_type: "bearer" },
  "GET /users/me": FAKE_USER,
};
const PAGE = { total: 0, limit: 100, offset: 0 };

afterEach(() => {
  tokenStore.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("createAppRouter", () => {
  it("shows the app's translated error screen and recovers with try again", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    let healthy = false;
    fakeApi({
      ...SESSION,
      "GET /notifications/unread-count": { count: 0 },
      "GET /projects": () => (healthy ? { ...PAGE, items: [] } : { ...PAGE, items: "malformed" }),
    });

    const { user } = await renderScreen("/projects", { signedIn: true });

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.queryByText(/Unexpected Application Error/)).not.toBeInTheDocument();

    healthy = true;
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
  });

  it("sends an unknown URL of a signed-out visitor to the login screen", async () => {
    fakeApi({ "GET /setup/status": { needs_setup: false } });
    await renderScreen("/no-such-page");
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });
});
