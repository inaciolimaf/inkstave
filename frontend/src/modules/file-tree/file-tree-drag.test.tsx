import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BASE, dragHandle, installFetch, renderPanel, row, we } from "./file-tree-test-helpers";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
  sessionStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

describe("FileTreePanel drag-and-drop", () => {
  it("moves an item by drag-and-drop onto a folder", async () => {
    const fetchMock = installFetch(BASE);
    renderPanel();
    await screen.findByText("main.tex");
    const dataTransfer = { setData: vi.fn(), getData: vi.fn() };
    fireEvent.dragStart(dragHandle("main.tex"), { dataTransfer });
    fireEvent.dragOver(dragHandle("Chapters"), { dataTransfer });
    fireEvent.drop(dragHandle("Chapters"), { dataTransfer });

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url).includes("/main/move") &&
            init?.method === "PATCH" &&
            JSON.parse(init.body as string).new_parent_id === "chapters",
        ),
      ).toBe(true),
    );
  });

  it("rejects dropping a folder into its own descendant", async () => {
    const fetchMock = installFetch([
      we("root", null, "folder", "root"),
      we("outer", "root", "folder", "Outer"),
      we("inner", "outer", "folder", "Inner"),
    ]);
    renderPanel();
    await screen.findByText("Outer");
    await userEvent.click(within(row("Outer")).getByRole("button", { name: "Expand folder" }));
    await screen.findByText("Inner");

    const dataTransfer = { setData: vi.fn(), getData: vi.fn() };
    fireEvent.dragStart(dragHandle("Outer"), { dataTransfer });
    fireEvent.drop(dragHandle("Inner"), { dataTransfer });

    expect(toast.error).toHaveBeenCalledWith("Can’t move a folder into itself");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/move"))).toBe(false);
  });

  it("ignores a drop of a folder onto itself", async () => {
    const fetchMock = installFetch(BASE);
    renderPanel();
    await screen.findByText("Chapters");
    const dataTransfer = { setData: vi.fn(), getData: vi.fn() };
    fireEvent.dragStart(dragHandle("Chapters"), { dataTransfer });
    fireEvent.drop(dragHandle("Chapters"), { dataTransfer });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/move"))).toBe(false);
  });
});
