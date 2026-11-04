import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { fakeApi } from "../../../tests/helpers/screen";
import { ProjectIndex } from "./project-index";
import type { ListedProject } from "./types";

vi.mock("@/lib/route-chunks", () => ({ loadEditorRoute: vi.fn(async () => undefined) }));

const PROJECT = {
  id: "p1",
  name: "Thesis",
  updatedAt: "2026-01-01T00:00:00Z",
  role: "owner",
  owner: { id: "u", displayName: "Me" },
} as ListedProject;
const ACTIONS = { onOpen: vi.fn(), onRename: vi.fn(), onDelete: vi.fn(), onLeave: vi.fn() };

describe("ProjectIndex", () => {
  it("fetches the project once when a pointer and then focus land on its link", async () => {
    const api = fakeApi({ "GET /projects/p1": { id: "p1", name: "Thesis" } });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ProjectIndex projects={[PROJECT]} {...ACTIONS} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const link = screen.getByRole("link", { name: "Thesis" });

    fireEvent.pointerEnter(link);
    await waitFor(() => expect(api.calls("GET /projects/p1")).toHaveLength(1));
    fireEvent.focus(link);

    await new Promise((resolve) => setTimeout(resolve));
    expect(api.calls("GET /projects/p1")).toHaveLength(1);
  });
});
