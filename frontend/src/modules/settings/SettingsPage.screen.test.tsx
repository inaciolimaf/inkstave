import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "@/lib/token-store";

import { FAKE_USER, expectOneManuscript, fakeApi, renderScreen } from "../../../tests/helpers/screen";

afterEach(() => {
  tokenStore.clear();
  vi.unstubAllGlobals();
});

describe("/settings", () => {
  it("is one sheet with one main, one h1 and a heading per section", async () => {
    fakeApi({
      "POST /auth/refresh": { access_token: "a", refresh_token: "r", token_type: "bearer" },
      "GET /users/me": FAKE_USER,
      "GET /notifications/unread-count": { count: 0 },
    });

    await renderScreen("/settings", { signedIn: true });

    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
    expectOneManuscript();
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent)).toEqual([
      "Profile",
      "Editor preferences",
      "Personal dictionary",
      "Email",
      "Password",
      "Delete account",
    ]);
  });
});
