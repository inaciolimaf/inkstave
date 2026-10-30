import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BASE, installFetch, renderPanel, row } from "./file-tree-test-helpers";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
  sessionStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

// --- Full keyboard model (issue 56 / spec 17 §8 + §5.3) ------------------ //

describe("FileTreePanel keyboard model", () => {
  it("F2 enters rename mode on the focused node", async () => {
    installFetch(BASE);
    renderPanel();
    await screen.findByText("main.tex");
    const tree = screen.getByRole("tree");
    // Roving-tabindex focus is internal; move it onto main.tex with End first.
    fireEvent.keyDown(tree, { key: "End" });
    await waitFor(() => expect(row("main.tex")).toHaveAttribute("tabindex", "0"));
    fireEvent.keyDown(tree, { key: "F2" });
    // startRename is deferred via setTimeout, so wait for the inline input.
    expect(await screen.findByLabelText("New name")).toBeInTheDocument();
  });

  it("Enter activates the focused node (opens a doc)", async () => {
    installFetch(BASE);
    const onSelect = renderPanel();
    await screen.findByText("main.tex");
    const tree = screen.getByRole("tree");
    // The keyboard model tracks focus via roving tabindex, not raw DOM focus, so
    // drive focus onto main.tex with End (last visible node) before Enter.
    fireEvent.keyDown(tree, { key: "End" });
    await waitFor(() => expect(row("main.tex")).toHaveAttribute("tabindex", "0"));
    fireEvent.keyDown(tree, { key: "Enter" });
    await waitFor(() =>
      expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "main", type: "doc" })),
    );
  });

  it("Delete opens the delete confirmation dialog", async () => {
    installFetch(BASE);
    renderPanel();
    await screen.findByText("main.tex");
    const tree = screen.getByRole("tree");
    // Move roving-tabindex focus onto main.tex before pressing Delete.
    fireEvent.keyDown(tree, { key: "End" });
    await waitFor(() => expect(row("main.tex")).toHaveAttribute("tabindex", "0"));
    fireEvent.keyDown(tree, { key: "Delete" });
    expect(await screen.findByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  it("Home and End jump focus to the first and last visible nodes", async () => {
    installFetch(BASE);
    renderPanel();
    await screen.findByText("main.tex");
    const tree = screen.getByRole("tree");
    // Visible order: Chapters (first), main.tex (last) — root is not rendered as a row.
    row("main.tex").focus();
    fireEvent.keyDown(tree, { key: "Home" });
    await waitFor(() => expect(row("Chapters")).toHaveAttribute("tabindex", "0"));
    fireEvent.keyDown(tree, { key: "End" });
    await waitFor(() => expect(row("main.tex")).toHaveAttribute("tabindex", "0"));
  });

  it("type-ahead moves focus to the node matching the typed letter", async () => {
    installFetch(BASE);
    renderPanel();
    await screen.findByText("main.tex");
    const tree = screen.getByRole("tree");
    // Start on Chapters; typing "m" should jump to main.tex.
    row("Chapters").focus();
    fireEvent.keyDown(tree, { key: "m" });
    await waitFor(() => expect(row("main.tex")).toHaveAttribute("tabindex", "0"));
  });
});
