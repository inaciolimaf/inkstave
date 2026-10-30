import { act, render, screen, waitFor } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";

import { fakeApi, renderScreen } from "./helpers/screen";

const STATIC_TITLE = "Inkstave — Write LaTeX like literature";

beforeEach(() => {
  document.title = STATIC_TITLE;
  fakeApi({ "GET /setup/status": { needs_setup: false } });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AppShell", () => {
  it("offers the skip link first, and it moves focus to the main landmark", async () => {
    const { user } = await renderScreen("/login");
    const heading = await screen.findByRole("heading", { level: 1, name: "Sign in to Inkstave" });

    await user.tab();
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveFocus();

    await user.keyboard("{Enter}");
    expect(heading.closest("main")).toHaveFocus();
  });

  it("leaves focus alone on the first load", async () => {
    await renderScreen("/login");
    await screen.findByRole("heading", { level: 1 });
    expect(document.body).toHaveFocus();
  });

  it("moves focus to the new screen's heading after a navigation", async () => {
    const { router, user } = await renderScreen("/login");
    await screen.findByRole("heading", { level: 1 });

    await act(() => router.navigate("/register"));

    const heading = await screen.findByRole("heading", { level: 1, name: "Create your account" });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(heading).toHaveAttribute("tabindex", "-1");
    expect(heading.style.outline).toContain("none");

    await user.tab();
    expect(heading).not.toHaveFocus();
    expect(heading).not.toHaveAttribute("tabindex");
  });

  it("falls back to the main landmark on a screen without a heading", async () => {
    const router = createMemoryRouter(
      [
        {
          element: <AppShell />,
          children: [
            { path: "/", element: <main>Start</main> },
            { path: "/plain", element: <main>Plain</main> },
          ],
        },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);

    await act(() => router.navigate("/plain"));

    expect(screen.getByRole("main")).toHaveFocus();
  });

  it("titles each screen, and gives the landing back its own title", async () => {
    const { router } = await renderScreen("/login");
    await waitFor(() => expect(document.title).toBe("Sign in — Inkstave"));

    await act(() => router.navigate("/register"));
    await waitFor(() => expect(document.title).toBe("Create account — Inkstave"));

    await act(() => router.navigate("/"));
    await waitFor(() => expect(document.title).toBe(STATIC_TITLE));
  });
});
