import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UnsavedChangesGuard } from "./unsaved-changes-guard";

function Home({ when }: { when: boolean }) {
  return (
    <div>
      <Link to="/other">Go elsewhere</Link>
      <UnsavedChangesGuard when={when} />
    </div>
  );
}

function renderApp(when: boolean) {
  const router = createMemoryRouter(
    [
      { path: "/", element: <Home when={when} /> },
      { path: "/other", element: <div>Other page</div> },
    ],
    { initialEntries: ["/"] },
  );
  return render(<RouterProvider router={router} />);
}

afterEach(() => vi.restoreAllMocks());

describe("UnsavedChangesGuard", () => {
  it("blocks in-app navigation while dirty and lets the user stay", async () => {
    renderApp(true);
    await userEvent.click(screen.getByRole("link", { name: "Go elsewhere" }));
    expect(await screen.findByText(/Leave with unsaved changes/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Stay" }));
    expect(screen.queryByText("Other page")).not.toBeInTheDocument();
  });

  it("allows navigation when there are no unsaved changes", async () => {
    renderApp(false);
    await userEvent.click(screen.getByRole("link", { name: "Go elsewhere" }));
    expect(await screen.findByText("Other page")).toBeInTheDocument();
  });

  it("registers a beforeunload handler while dirty", () => {
    const addSpy = vi.spyOn(window, "addEventListener");
    renderApp(true);
    expect(addSpy.mock.calls.some(([event]) => event === "beforeunload")).toBe(true);
  });
});
