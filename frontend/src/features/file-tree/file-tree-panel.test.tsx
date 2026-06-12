import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FileTreePanel } from "./file-tree-panel";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

interface WE {
  id: string;
  project_id: string;
  parent_id: string | null;
  type: "folder" | "doc" | "file";
  name: string;
  is_root: boolean;
  path: string;
}

function we(id: string, parent: string | null, type: WE["type"], name: string): WE {
  return { id, project_id: "p", parent_id: parent, type, name, is_root: id === "root", path: name };
}

function buildTree(entities: WE[]): unknown {
  const build = (n: WE): unknown => ({
    ...n,
    children: entities.filter((e) => e.parent_id === n.id).map(build),
  });
  return build(entities.find((e) => e.is_root)!);
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function descendants(entities: WE[], id: string): Set<string> {
  const ids = new Set([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const e of entities) {
      if (e.parent_id && ids.has(e.parent_id) && !ids.has(e.id)) {
        ids.add(e.id);
        grew = true;
      }
    }
  }
  return ids;
}

function installFetch(initial: WE[]) {
  let entities = [...initial];
  let counter = 0;
  const fetchMock = vi.fn(async (input: string | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const method = init?.method ?? "GET";
    if (path.endsWith("/tree") && method === "GET") return json({ root: buildTree(entities) }, 200);
    if (path.endsWith("/tree/entities") && method === "POST") {
      const body = JSON.parse(init!.body as string) as {
        type: WE["type"];
        name: string;
        parent_id: string | null;
      };
      const ent = we(`e${++counter}`, body.parent_id ?? "root", body.type, body.name);
      entities.push(ent);
      return json(ent, 201);
    }
    const rn = path.match(/\/tree\/entities\/([^/]+)\/rename$/);
    if (rn && method === "PATCH") {
      const body = JSON.parse(init!.body as string) as { name: string };
      entities = entities.map((e) => (e.id === rn[1] ? { ...e, name: body.name } : e));
      return json(
        entities.find((e) => e.id === rn[1]),
        200,
      );
    }
    const mv = path.match(/\/tree\/entities\/([^/]+)\/move$/);
    if (mv && method === "PATCH") {
      const body = JSON.parse(init!.body as string) as { new_parent_id: string };
      entities = entities.map((e) =>
        e.id === mv[1] ? { ...e, parent_id: body.new_parent_id } : e,
      );
      return json(
        entities.find((e) => e.id === mv[1]),
        200,
      );
    }
    const del = path.match(/\/tree\/entities\/([^/]+)$/);
    if (del && method === "DELETE") {
      const ids = descendants(entities, del[1]);
      entities = entities.filter((e) => !ids.has(e.id));
      return new Response(null, { status: 204 });
    }
    return new Response("nf", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const BASE: WE[] = [
  we("root", null, "folder", "root"),
  we("chapters", "root", "folder", "Chapters"),
  we("intro", "chapters", "doc", "intro.tex"),
  we("main", "root", "doc", "main.tex"),
];

function renderPanel(onSelect = vi.fn()) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <FileTreePanel projectId="p" selectedId={null} onSelectEntity={onSelect} />
    </QueryClientProvider>,
  );
  return onSelect;
}

const row = (name: string) => screen.getByText(name).closest('[role="treeitem"]') as HTMLElement;
const dragHandle = (name: string) =>
  screen.getByText(name).closest('[draggable="true"]') as HTMLElement;

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
});
