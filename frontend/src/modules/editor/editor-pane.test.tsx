// The pane mounts the live CRDT editor for a document (spec 31). The WebSocket session and the
// editor itself are replaced here: their own tests cover them. This file covers the pane's
// shell: what it shows for each selection, the 404 path, settings and the save shortcut.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TreeEntity } from "@/modules/file-tree/types";

import { EditorPane } from "./editor-pane";

const flush = vi.hoisted(() => vi.fn(() => Promise.resolve()));

vi.mock("@/modules/collab", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/modules/collab")>()),
  useCollabDoc: ({ documentId }: { documentId: string | null }) =>
    documentId ? { label: `session:${documentId}`, flush } : null,
}));

vi.mock("./CollabEditor", async () => {
  const { createElement } = await import("react");
  return {
    CollabEditor: ({ session }: { session: { label: string } }) =>
      createElement("div", { "data-testid": "collab-editor" }, session.label),
  };
});

// The editor reads server-side preferences (spec 59); provide a stub user.
const auth = vi.hoisted(() => ({
  user: {
    id: "u1",
    editor_preferences: { theme: "system", font_size: 14, keymap: "default" },
  },
  applyUser: vi.fn(),
}));
vi.mock("@/modules/auth/auth-context", () => ({ useAuth: () => auth }));

function entity(over: Partial<TreeEntity>): TreeEntity {
  return {
    id: "d1",
    name: "main.tex",
    type: "doc",
    parentId: "root",
    isRoot: false,
    path: "main.tex",
    ...over,
  };
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function docWire(id: string, content: string, version: number) {
  return {
    entity_id: id,
    project_id: "p",
    version,
    size_bytes: content.length,
    content,
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function PaneWithClient({ selected, onClear }: { selected: TreeEntity | null; onClear: () => void }) {
  const [qc] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
      }),
  );
  return (
    <QueryClientProvider client={qc}>
      <EditorPane projectId="p" selected={selected} onClearSelection={onClear} />
    </QueryClientProvider>
  );
}

function renderPane(selected: TreeEntity | null, onClear = vi.fn()) {
  const utils = render(<PaneWithClient selected={selected} onClear={onClear} />);
  return { ...utils, onClear };
}

beforeEach(() => {
  localStorage.clear();
  flush.mockClear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => json(docWire("d1", "hello", 1), 200)),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("EditorPane", () => {
  it("shows the empty state with no selection", () => {
    renderPane(null);
    expect(screen.getByText(/select a file/i)).toBeInTheDocument();
  });

  it("ignores folder selection (no document opened)", () => {
    renderPane(entity({ type: "folder", name: "Chapters" }));
    expect(screen.getByText(/select a file/i)).toBeInTheDocument();
  });

  it("shows the binary notice for a file entity", () => {
    renderPane(entity({ type: "file", name: "data.zip" }));
    expect(screen.getByText(/binary file/i)).toBeInTheDocument();
  });

  it("mounts the live editor for the selected document and follows a switch", async () => {
    const { rerender, onClear } = renderPane(entity({ id: "d1" }));
    expect(await screen.findByText("session:d1")).toBeInTheDocument();

    rerender(<PaneWithClient selected={entity({ id: "d2", name: "other.tex" })} onClear={onClear} />);
    expect(await screen.findByText("session:d2")).toBeInTheDocument();
  });

  it("clears the selection on a 404", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ error: { type: "entity_not_found" } }, 404)),
    );
    const { onClear } = renderPane(entity({ id: "gone" }));
    await waitFor(() => expect(onClear).toHaveBeenCalled());
  });

  it("changes a setting live and persists it", async () => {
    renderPane(entity({ id: "d1" }));
    await screen.findByTestId("collab-editor");

    await userEvent.click(screen.getByRole("button", { name: "Editor settings" }));
    await userEvent.click(await screen.findByRole("switch", { name: "Line wrapping" }));
    await waitFor(() =>
      expect(JSON.parse(localStorage.getItem("inkstave:editor-settings")!).lineWrapping).toBe(false),
    );
  });

  // Spec 19 AC11 / issue 69: Ctrl/Cmd+S waits for the server to hold the edits and suppresses
  // the browser's native save dialog.
  it.each<[string, KeyboardEventInit]>([
    ["Ctrl+S", { key: "s", ctrlKey: true }],
    ["Cmd+S", { key: "s", metaKey: true }],
  ])("flushes the live session and suppresses the native dialog on %s", async (_name, modifier) => {
    renderPane(entity({ id: "d1" }));
    await screen.findByTestId("collab-editor");

    const event = new KeyboardEvent("keydown", { ...modifier, cancelable: true, bubbles: true });
    window.dispatchEvent(event);

    expect(flush).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });
});
