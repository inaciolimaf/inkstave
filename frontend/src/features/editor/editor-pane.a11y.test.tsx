import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TreeEntity } from "@/features/file-tree/types";

import { EditorPane } from "./editor-pane";

expect.extend(toHaveNoViolations);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const auth = vi.hoisted(() => ({
  user: { id: "u1", editor_preferences: { theme: "system", font_size: 14, keymap: "default" } },
  applyUser: vi.fn(),
}));
vi.mock("@/auth/auth-context", () => ({ useAuth: () => auth }));

const DOC: TreeEntity = {
  id: "d1",
  name: "main.tex",
  type: "doc",
  parentId: "root",
  isRoot: false,
  path: "main.tex",
};

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            entity_id: "d1",
            project_id: "p",
            version: 1,
            size_bytes: 5,
            content: "\\section{Hi}",
            updated_at: "2026-01-01T00:00:00Z",
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
    ),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("EditorPane accessibility", () => {
  it("has no serious/critical axe violations with a document open", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <EditorPane projectId="p" selected={DOC} onClearSelection={vi.fn()} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(container.querySelector(".cm-content")).toBeTruthy());
    expect(screen.getByLabelText("LaTeX editor")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });
});
