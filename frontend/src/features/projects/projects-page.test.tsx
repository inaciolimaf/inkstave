import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectsPage } from "./projects-page";

vi.mock("@/auth/auth-context", () => ({ useAuth: () => ({ logout: vi.fn() }) }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

interface Wire {
  id: string;
  name: string;
  owner_id: string;
  root_doc_id: string | null;
  created_at: string;
  updated_at: string;
}

function wire(id: string, name: string, updated = "2026-01-01T00:00:00Z"): Wire {
  return { id, name, owner_id: "u", root_doc_id: null, created_at: updated, updated_at: updated };
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function installFetch(initial: Wire[]) {
  let store = [...initial];
  let counter = 0;
  const fetchMock = vi.fn(async (input: string | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = init?.method ?? "GET";
    const path = url.pathname;
    if (path === "/api/v1/projects" && method === "GET") {
      return json({ items: store, total: store.length }, 200);
    }
    if (path === "/api/v1/projects" && method === "POST") {
      const body = JSON.parse(init!.body as string) as { name: string };
      const created = wire(`new-${++counter}`, body.name, "2026-12-31T00:00:00Z");
      store = [created, ...store];
      return json(created, 201);
    }
    const match = path.match(/^\/api\/v1\/projects\/(.+)$/);
    if (match) {
      const id = match[1];
      if (method === "PATCH") {
        const body = JSON.parse(init!.body as string) as { name: string };
        store = store.map((p) => (p.id === id ? { ...p, name: body.name } : p));
        return json(
          store.find((p) => p.id === id),
          200,
        );
      }
      if (method === "DELETE") {
        store = store.filter((p) => p.id !== id);
        return new Response(null, { status: 204 });
      }
      if (method === "GET")
        return json(
          store.find((p) => p.id === id),
          200,
        );
    }
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/projects"]}>
        <Routes>
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<div>Editor shell</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// The dashboard renders both a table (md+) and a card grid (< md); jsdom keeps
// both in the DOM, so project links appear twice. Assert on "at least one".
const hasLink = async (name: string) =>
  expect((await screen.findAllByRole("link", { name })).length).toBeGreaterThan(0);
const noLink = (name: string) => expect(screen.queryAllByRole("link", { name })).toHaveLength(0);

async function openRowMenu(name: string) {
  const row = screen.getByRole("row", { name: new RegExp(name) });
  await userEvent.click(within(row).getByRole("button", { name: "Project actions" }));
}

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
});
afterEach(() => vi.unstubAllGlobals());

describe("ProjectsPage", () => {
  it("renders the fetched projects in a table", async () => {
    installFetch([wire("1", "Alpha"), wire("2", "Beta")]);
    renderPage();
    await hasLink("Alpha");
    await hasLink("Beta");
  });

  it("creates a project and shows it in the list", async () => {
    const fetchMock = installFetch([wire("1", "Alpha")]);
    renderPage();
    await hasLink("Alpha");

    await userEvent.click(screen.getByRole("button", { name: /new project/i }));
    await userEvent.type(await screen.findByLabelText("Project name"), "Gamma");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));

    await hasLink("Gamma");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true);
    expect(toast.success).toHaveBeenCalledWith("Project created");
  });

  it("renames a project optimistically", async () => {
    const fetchMock = installFetch([wire("1", "Alpha")]);
    renderPage();
    await hasLink("Alpha");

    await openRowMenu("Alpha");
    await userEvent.click(await screen.findByRole("menuitem", { name: "Rename" }));
    const input = await screen.findByLabelText("Project name");
    await userEvent.clear(input);
    await userEvent.type(input, "Renamed");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await hasLink("Renamed");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true);
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Project renamed"));
  });

  it("deletes a project after confirmation", async () => {
    const fetchMock = installFetch([wire("1", "Alpha"), wire("2", "Beta")]);
    renderPage();
    await hasLink("Alpha");

    await openRowMenu("Alpha");
    await userEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));

    await waitFor(() => noLink("Alpha"));
    await hasLink("Beta");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(true);
  });

  it("opens a project by navigating to its editor route", async () => {
    installFetch([wire("1", "Alpha")]);
    renderPage();
    await userEvent.click((await screen.findAllByRole("link", { name: "Alpha" }))[0]);
    expect(await screen.findByText("Editor shell")).toBeInTheDocument();
  });

  it("filters the list with the search box", async () => {
    installFetch([wire("1", "Alpha"), wire("2", "Beta")]);
    renderPage();
    await hasLink("Alpha");

    await userEvent.type(screen.getByLabelText("Search projects"), "bet");
    await waitFor(() => noLink("Alpha"));
    await hasLink("Beta");
  });

  it("rolls back an optimistic rename when the request fails", async () => {
    // GET succeeds (stable), PATCH fails -> the optimistic name must revert.
    const fetchMock = vi.fn(async (input: string | URL, init?: RequestInit) => {
      const path = new URL(String(input), "http://localhost").pathname;
      const method = init?.method ?? "GET";
      if (path === "/api/v1/projects" && method === "GET") {
        return json({ items: [wire("1", "Alpha")], total: 1 }, 200);
      }
      if (method === "PATCH") return json({ error: { type: "server_error" } }, 500);
      return new Response(null, { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await hasLink("Alpha");

    await openRowMenu("Alpha");
    await userEvent.click(await screen.findByRole("menuitem", { name: "Rename" }));
    const input = await screen.findByLabelText("Project name");
    await userEvent.clear(input);
    await userEvent.type(input, "Renamed");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Could not rename project"));
    // Close the (still-open) dialog so the list re-enters the a11y tree.
    await userEvent.keyboard("{Escape}");
    await hasLink("Alpha");
    expect(screen.queryAllByRole("link", { name: "Renamed" })).toHaveLength(0);
  });

  it("rolls back an optimistic delete when the request fails", async () => {
    // GET succeeds (stable), DELETE fails -> the project must reappear.
    const fetchMock = vi.fn(async (input: string | URL, init?: RequestInit) => {
      const path = new URL(String(input), "http://localhost").pathname;
      const method = init?.method ?? "GET";
      if (path === "/api/v1/projects" && method === "GET") {
        return json({ items: [wire("1", "Alpha"), wire("2", "Beta")], total: 2 }, 200);
      }
      if (method === "DELETE") return json({ error: { type: "server_error" } }, 500);
      return new Response(null, { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await hasLink("Alpha");

    await openRowMenu("Alpha");
    await userEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));

    // An error toast is requested and the optimistically-removed project reappears.
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Could not delete project"));
    await hasLink("Alpha");
    await hasLink("Beta");
  });
});
