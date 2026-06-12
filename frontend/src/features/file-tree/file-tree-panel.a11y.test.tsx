import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FileTreePanel } from "./file-tree-panel";

expect.extend(toHaveNoViolations);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const TREE = {
  root: {
    id: "root",
    project_id: "p",
    parent_id: null,
    type: "folder",
    name: "root",
    is_root: true,
    path: "",
    children: [
      {
        id: "chapters",
        project_id: "p",
        parent_id: "root",
        type: "folder",
        name: "Chapters",
        is_root: false,
        path: "Chapters",
        children: [],
      },
      {
        id: "main",
        project_id: "p",
        parent_id: "root",
        type: "doc",
        name: "main.tex",
        is_root: false,
        path: "main.tex",
        children: null,
      },
    ],
  },
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(TREE), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    ),
  );
  sessionStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

describe("FileTreePanel accessibility", () => {
  it("has no serious/critical axe violations and a valid ARIA tree", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <FileTreePanel projectId="p" selectedId={null} onSelectEntity={vi.fn()} />
      </QueryClientProvider>,
    );
    await screen.findByRole("tree", { name: "Project files" });
    expect(screen.getAllByRole("treeitem").length).toBeGreaterThan(0);
    expect(await axe(container)).toHaveNoViolations();
  });
});
