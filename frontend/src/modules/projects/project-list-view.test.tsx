import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { ProjectListView } from "./project-list-view";
import type { Project } from "./types";

const sample: Project[] = [
  {
    id: "1",
    name: "My Paper",
    ownerId: "u",
    rootDocId: null,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-02T00:00:00Z",
  },
];

type Props = React.ComponentProps<typeof ProjectListView>;

function queryWith(overrides: Partial<Props["query"]> = {}): Props["query"] {
  return { data: sample, isLoading: false, isError: false, refetch: vi.fn(), ...overrides };
}

function renderView(props: Partial<Props> = {}) {
  const base: Props = {
    query: queryWith(),
    searchTerm: "",
    visible: sample,
    onCreate: vi.fn(),
    onClearSearch: vi.fn(),
    onOpen: vi.fn(),
    onRename: vi.fn(),
    onDelete: vi.fn(),
  };
  return renderWithProviders(<ProjectListView {...base} {...props} />);
}

describe("ProjectListView", () => {
  it("shows a skeleton while loading", () => {
    renderView({ query: queryWith({ data: undefined, isLoading: true }) });
    expect(screen.getByLabelText("Loading projects")).toBeInTheDocument();
  });

  it("shows the empty state when there are no projects", async () => {
    const onCreate = vi.fn();
    renderView({ query: queryWith({ data: [] }), visible: [], onCreate });
    expect(screen.getByText("No projects yet")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /create your first project/i }));
    expect(onCreate).toHaveBeenCalled();
  });

  it("shows the error state with a working Retry", async () => {
    const refetch = vi.fn();
    renderView({ query: queryWith({ data: undefined, isError: true, refetch }) });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("shows the no-results state when a filter excludes everything", async () => {
    const onClearSearch = vi.fn();
    renderView({ visible: [], searchTerm: "zzz", onClearSearch });
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
