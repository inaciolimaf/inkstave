import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ProjectListView } from "./project-list-view";
import type { Project } from "./types";

const sample: Project[] = [
  {
    id: "1",
    name: "My Paper",
    ownerId: "u",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-02T00:00:00Z",
  },
];

function renderView(props: Partial<React.ComponentProps<typeof ProjectListView>> = {}) {
  const base: React.ComponentProps<typeof ProjectListView> = {
    isLoading: false,
    isError: false,
    onRetry: vi.fn(),
    total: sample.length,
    searchTerm: "",
    visible: sample,
    onCreate: vi.fn(),
    onClearSearch: vi.fn(),
    onOpen: vi.fn(),
    onRename: vi.fn(),
    onDelete: vi.fn(),
  };
  return render(
    <MemoryRouter>
      <ProjectListView {...base} {...props} />
    </MemoryRouter>,
  );
}

describe("ProjectListView", () => {
  it("shows a skeleton while loading", () => {
    renderView({ isLoading: true });
    expect(screen.getByLabelText("Loading projects")).toBeInTheDocument();
  });

  it("shows the empty state when there are no projects", async () => {
    const onCreate = vi.fn();
    renderView({ total: 0, visible: [], onCreate });
    expect(screen.getByText("No projects yet")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /create your first project/i }));
    expect(onCreate).toHaveBeenCalled();
  });

  it("shows the error state with a working Retry", async () => {
    const onRetry = vi.fn();
    renderView({ isError: true, onRetry });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("shows the no-results state when a filter excludes everything", async () => {
    const onClearSearch = vi.fn();
    renderView({ total: 1, visible: [], searchTerm: "zzz", onClearSearch });
    expect(screen.getByText(/No projects match/)).toHaveTextContent("zzz");
    await userEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(onClearSearch).toHaveBeenCalled();
  });

  it("renders the table with project rows on success", () => {
    renderView();
    const link = screen.getAllByRole("link", { name: "My Paper" })[0];
    expect(link).toHaveAttribute("href", "/projects/1");
  });
});
