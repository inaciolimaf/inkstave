import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BASE, buildTree, installFetch, json, renderPanel, row } from "./file-tree-test-helpers";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
  sessionStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

describe("FileTreePanel CRUD", () => {
  it("creates a document via the toolbar", async () => {
    const fetchMock = installFetch(BASE);
    renderPanel();
    await screen.findByText("main.tex");
    await userEvent.click(screen.getByRole("button", { name: "New file" }));
    const input = await screen.findByLabelText("Name");
    await userEvent.clear(input);
    await userEvent.type(input, "new.tex");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByText("new.tex")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([, init]) => init?.method === "POST" && JSON.parse(init.body as string).name === "new.tex",
      ),
    ).toBe(true);
  });

  it("blocks invalid create names", async () => {
    installFetch(BASE);
    renderPanel();
    await screen.findByText("main.tex");
    await userEvent.click(screen.getByRole("button", { name: "New folder" }));
    const input = await screen.findByLabelText("Name");
    await userEvent.clear(input);
    await userEvent.type(input, "a/b");
    expect(screen.getByText(/cannot contain slashes/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
  });

  it("renames via the row menu", async () => {
    const fetchMock = installFetch(BASE);
    renderPanel();
    await screen.findByText("main.tex");
    await userEvent.click(
      within(row("main.tex")).getByRole("button", { name: "Actions for main.tex" }),
    );
    await userEvent.click(await screen.findByRole("menuitem", { name: "Rename" }));
    const input = await screen.findByLabelText("New name");
    await userEvent.clear(input);
    await userEvent.type(input, "renamed.tex{Enter}");

    expect(await screen.findByText("renamed.tex")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) => String(url).includes("/rename") && init?.method === "PATCH",
      ),
    ).toBe(true);
  });

  it("deletes a folder after a warning confirm", async () => {
    const fetchMock = installFetch(BASE);
    renderPanel();
    await screen.findByText("Chapters");
    await userEvent.click(
      within(row("Chapters")).getByRole("button", { name: "Actions for Chapters" }),
    );
    await userEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));
    expect(
      screen.getByText(/everything inside it will be permanently deleted/i),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(screen.queryByText("Chapters")).not.toBeInTheDocument());
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) => init?.method === "DELETE" && String(url).includes("/chapters"),
      ),
    ).toBe(true);
  });

  it("rolls back an optimistic delete when the request fails", async () => {
    const fetchMock = vi.fn(async (input: string | URL, init?: RequestInit) => {
      const path = new URL(String(input), "http://localhost").pathname;
      const method = init?.method ?? "GET";
      if (path.endsWith("/tree") && method === "GET") return json({ root: buildTree(BASE) }, 200);
      if (method === "DELETE") return json({ error: { type: "server_error" } }, 500);
      return new Response("nf", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPanel();
    await screen.findByText("main.tex");

    await userEvent.click(
      within(row("main.tex")).getByRole("button", { name: "Actions for main.tex" }),
    );
    await userEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));

    // Optimistically removed, then restored after the failure.
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Could not delete item"));
    expect(await screen.findByText("main.tex")).toBeInTheDocument();
  });
});
