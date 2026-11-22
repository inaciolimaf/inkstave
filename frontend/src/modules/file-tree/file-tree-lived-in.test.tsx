import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installLivedInFetch, LIVED } from "@/test/lived-in";

import { FileTreePanel } from "./file-tree-panel";
import { row } from "./file-tree-test-helpers";

beforeEach(() => sessionStorage.clear());
afterEach(() => vi.unstubAllGlobals());

function renderLivedInTree(onSelect = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={qc}>
      <FileTreePanel projectId={LIVED.projectId} selectedId={null} onSelectEntity={onSelect} />
    </QueryClientProvider>,
  );
  return onSelect;
}

describe("FileTreePanel on a lived-in project", () => {
  it("shows the files that already exist at the root and in their folders", async () => {
    installLivedInFetch();
    renderLivedInTree();

    expect(await screen.findByText("main.tex")).toBeInTheDocument();
    expect(screen.getByText("refs.bib")).toBeInTheDocument();
    expect(screen.getByText("appendix.tex")).toBeInTheDocument();

    await userEvent.click(within(row("chapters")).getByRole("button", { name: "Expand folder" }));
    expect(await screen.findByText("intro.tex")).toBeInTheDocument();
    expect(screen.getByText("methods.tex")).toBeInTheDocument();

    await userEvent.click(within(row("figures")).getByRole("button", { name: "Expand folder" }));
    expect(await screen.findByText("plot.png")).toBeInTheDocument();
  });

  it("selects a seeded chapter with its own id", async () => {
    installLivedInFetch();
    const onSelect = renderLivedInTree();
    await screen.findByText("chapters");
    await userEvent.click(within(row("chapters")).getByRole("button", { name: "Expand folder" }));
    await userEvent.click(await screen.findByText("intro.tex"));

    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: LIVED.ids.intro, type: "doc" }));
  });
});
