// Mocking strategy (spec 18 §8): the spec prescribes mocking the Spec-13 document
// API. MSW is intentionally NOT a dependency of this project; instead we adopt the
// lightweight, dependency-free strategy used project-wide — stubbing `fetch` via
// `vi.stubGlobal` for both the GET (load content) and PUT (save content) paths.
// This satisfies §8's intent ("the Spec-13 API is mocked") without adding MSW.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TreeEntity } from "@/features/file-tree/types";

import { EditorPane } from "./editor-pane";

// The editor reads server-side preferences (spec 59); provide a stub user.
const auth = vi.hoisted(() => ({
  user: {
    id: "u1",
    editor_preferences: { theme: "system", font_size: 14, keymap: "default" },
  },
  applyUser: vi.fn(),
}));
vi.mock("@/auth/auth-context", () => ({ useAuth: () => auth }));

// Issue 69 (spec 19 AC11): wrap the real autosave hook so the Ctrl/Cmd+S keydown
// handler can be exercised with `saveNow` as a spy. Delegating to the actual hook
// keeps every other test's autosave behaviour (displayText, version) intact.
const autosave = vi.hoisted(() => ({ saveNow: vi.fn() }));
vi.mock("./autosave/use-document-autosave", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./autosave/use-document-autosave")>();
  return {
    ...actual,
    useDocumentAutosave: (...args: Parameters<typeof actual.useDocumentAutosave>) => {
      const real = actual.useDocumentAutosave(...args);
      autosave.saveNow.mockImplementation(real.saveNow);
      return { ...real, saveNow: autosave.saveNow };
    },
  };
});

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

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderPane(selected: TreeEntity | null, onClear = vi.fn()) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={qc}>
      <EditorPane projectId="p" selected={selected} onClearSelection={onClear} />
    </QueryClientProvider>,
  );
  return { ...utils, onClear };
}

const cmText = (c: ParentNode) => c.querySelector(".cm-content")?.textContent ?? "";

beforeEach(() => {
  localStorage.clear();
  autosave.saveNow.mockClear();
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
    renderPane(entity({ type: "file", name: "logo.png" }));
    expect(screen.getByText(/binary file/i)).toBeInTheDocument();
  });

  it("loads and displays a document with a save-status indicator", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(docWire("d1", "\\documentclass{article}", 3), 200)),
    );
    const { container } = renderPane(entity({ id: "d1" }));
    await waitFor(() => expect(cmText(container)).toContain("documentclass"));
    expect(screen.getByText("Saved")).toBeInTheDocument();
    // Editable now (spec 19): the content region is no longer read-only.
    expect(container.querySelector(".cm-content")?.getAttribute("contenteditable")).not.toBe(
      "false",
    );
  });

  it("captures the document version (for autosave in spec 19)", async () => {
    const fetchMock = vi.fn<(input: string | URL) => Promise<Response>>(async () =>
      json(docWire("d1", "hi", 7), 200),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderPane(entity({ id: "d1" }));
    await waitFor(() => expect(cmText(container)).toContain("hi"));
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/projects/p/documents/d1");
  });

  it("swaps content when switching documents", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL) => {
        const id = String(input).endsWith("/d2") ? "d2" : "d1";
        return json(docWire(id, id === "d2" ? "second doc" : "first doc", 1), 200);
      }),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container, rerender } = render(
      <QueryClientProvider client={qc}>
        <EditorPane projectId="p" selected={entity({ id: "d1" })} onClearSelection={vi.fn()} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(cmText(container)).toContain("first doc"));

    rerender(
      <QueryClientProvider client={qc}>
        <EditorPane
          projectId="p"
          selected={entity({ id: "d2", name: "other.tex" })}
          onClearSelection={vi.fn()}
        />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(cmText(container)).toContain("second doc"));
  });

  it("shows an error state with Retry on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ error: { type: "boom" } }, 500)),
    );
    renderPane(entity({ id: "d1" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
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
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(docWire("d1", "x", 1), 200)),
    );
    const { container } = renderPane(entity({ id: "d1" }));
    await waitFor(() => expect(cmText(container)).toContain("x"));

    await userEvent.click(screen.getByRole("button", { name: "Editor settings" }));
    await userEvent.click(await screen.findByRole("switch", { name: "Line wrapping" }));
    await waitFor(() =>
      expect(JSON.parse(localStorage.getItem("inkstave:editor-settings")!).lineWrapping).toBe(
        false,
      ),
    );
  });

  // Issue 69 / spec 19 AC11: Ctrl/Cmd+S flushes immediately and suppresses the
  // browser's native save dialog (preventDefault).
  it.each<[string, KeyboardEventInit]>([
    ["Ctrl+S", { key: "s", ctrlKey: true }],
    ["Cmd+S", { key: "s", metaKey: true }],
  ])("flushes and suppresses the native dialog on %s", async (_name, modifier) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(docWire("d1", "hi", 1), 200)),
    );
    const { container } = renderPane(entity({ id: "d1" }));
    await waitFor(() => expect(cmText(container)).toContain("hi"));

    const event = new KeyboardEvent("keydown", { ...modifier, cancelable: true, bubbles: true });
    window.dispatchEvent(event);

    expect(autosave.saveNow).toHaveBeenCalledTimes(1); // immediate flush
    expect(event.defaultPrevented).toBe(true); // native save dialog suppressed
  });
});
