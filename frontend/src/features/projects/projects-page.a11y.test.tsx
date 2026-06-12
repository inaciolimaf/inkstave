import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectsPage } from "./projects-page";

expect.extend(toHaveNoViolations);

vi.mock("@/auth/auth-context", () => ({ useAuth: () => ({ logout: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            items: [
              {
                id: "1",
                name: "Alpha",
                owner_id: "u",
                root_doc_id: null,
                created_at: "2026-01-01T00:00:00Z",
                updated_at: "2026-01-01T00:00:00Z",
              },
            ],
            total: 1,
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
    ),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("ProjectsPage accessibility", () => {
  it("has no serious/critical axe violations", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/projects"]}>
          <ProjectsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findAllByRole("link", { name: "Alpha" });
    expect(await axe(container)).toHaveNoViolations();
  });
});
