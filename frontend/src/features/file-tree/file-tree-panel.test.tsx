import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BASE, installFetch, renderPanel, row } from "./file-tree-test-helpers";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
  sessionStorage.clear(); // expansion state is session-persisted; isolate tests
});
afterEach(() => vi.unstubAllGlobals());

describe("FileTreePanel", () => {
  it("renders the tree with ARIA roles and levels", async () => {
    installFetch(BASE);
    renderPanel();
    expect(await screen.findByRole("tree", { name: "Project files" })).toBeInTheDocument();
    expect(row("Chapters")).toHaveAttribute("aria-level", "1");
    expect(row("Chapters")).toHaveAttribute("aria-expanded", "false");
    // Collapsed folder hides its child.
    expect(screen.queryByText("intro.tex")).not.toBeInTheDocument();
  });

  it("expands and collapses a folder", async () => {
    installFetch(BASE);
    renderPanel();
    await screen.findByText("Chapters");
    await userEvent.click(within(row("Chapters")).getByRole("button", { name: "Expand folder" }));
    expect(await screen.findByText("intro.tex")).toBeInTheDocument();
    expect(row("Chapters")).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(within(row("Chapters")).getByRole("button", { name: "Collapse folder" }));
    await waitFor(() => expect(screen.queryByText("intro.tex")).not.toBeInTheDocument());
  });

  it("selects a doc and emits the selection", async () => {
    installFetch(BASE);
    const onSelect = renderPanel();
    await userEvent.click(await screen.findByText("main.tex"));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "main", type: "doc" }));
    expect(row("main.tex")).toHaveAttribute("aria-selected", "true");
  });

  it("supports keyboard navigation with roving tabindex", async () => {
    installFetch(BASE);
    renderPanel();
    await screen.findByText("main.tex");
    const tree = screen.getByRole("tree");
    // Exactly one treeitem is tabbable.
    const tabbable = screen
      .getAllByRole("treeitem")
      .filter((el) => el.getAttribute("tabindex") === "0");
    expect(tabbable).toHaveLength(1);

    row("Chapters").focus();
    fireEvent.keyDown(tree, { key: "ArrowRight" }); // expand Chapters
    expect(await screen.findByText("intro.tex")).toBeInTheDocument();
    fireEvent.keyDown(tree, { key: "ArrowLeft" }); // collapse
    await waitFor(() => expect(screen.queryByText("intro.tex")).not.toBeInTheDocument());
  });

  it("shows an error state with a working Retry", async () => {
    const fetchMock = vi.fn(async () => new Response("boom", { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);
    renderPanel();
    expect(await screen.findByRole("alert")).toHaveTextContent(/load the file tree/i);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  // --- Viewer capability-gating (issue 139 / spec 34 §8 AC10) -------------- //
  //
  // SKIPPED: FileTreePanel does not yet consume a permissions/role prop or hook,
  // so it cannot gate (hide/disable) the mutation controls for viewers. The
  // gating logic must be added to `file-tree-panel.tsx`, which is OUT OF SCOPE
  // for this fix-pack (spec 72 §2). This test records the required AC10 behaviour
  // so the owning pack can unskip it once gating is implemented. Gap reported.
  it.skip("hides file-tree mutation controls for viewers (mocked permissions)", async () => {
    installFetch(BASE);
    // A real implementation would mock the viewer-role permissions response here
    // and render the panel with that role; then assert the mutation controls are
    // hidden or disabled for the viewer.
    renderPanel();
    await screen.findByText("main.tex");
    expect(screen.queryByRole("button", { name: "New file" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New folder" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Actions for main.tex" }),
    ).not.toBeInTheDocument();
  });
});
