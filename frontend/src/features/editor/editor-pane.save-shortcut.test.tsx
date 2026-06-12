import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TreeEntity } from "@/features/file-tree/types";

// Spy on the autosave hook so we can assert Ctrl/Cmd+S triggers `saveNow`
// (spec 19 AC11) without exercising the real network-backed autosave.
const saveNow = vi.hoisted(() => vi.fn());
vi.mock("./autosave/use-document-autosave", () => ({
  useDocumentAutosave: () => ({
    status: "clean" as const,
    displayText: "hello",
    hasUnsaved: false,
    conflict: null,
    lastSavedAt: null,
    onLocalChange: vi.fn(),
    saveNow,
    resolveReload: vi.fn(),
    resolveKeepMine: vi.fn(),
  }),
}));

const auth = vi.hoisted(() => ({
  user: {
    id: "u1",
    editor_preferences: { theme: "system", font_size: 14, keymap: "default" },
  },
  applyUser: vi.fn(),
}));
vi.mock("@/auth/auth-context", () => ({ useAuth: () => auth }));

import { EditorPane } from "./editor-pane";

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

function renderPane() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <EditorPane projectId="p" selected={entity({ id: "d1" })} onClearSelection={vi.fn()} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  saveNow.mockClear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => json(docWire("d1", "hello", 1), 200)),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("EditorPane Ctrl/Cmd+S shortcut (spec 19 AC11)", () => {
  it.each([{ ctrlKey: true }, { metaKey: true }])(
    "flushes a save and suppresses the native dialog (%o)",
    async (mods) => {
      const { container } = renderPane();
      // Wait for the document to load so the keydown handler is mounted.
      await waitFor(() => expect(container.querySelector(".cm-content")).toBeTruthy());

      const event = new KeyboardEvent("keydown", { key: "s", cancelable: true, ...mods });
      const prevented = !window.dispatchEvent(event);

      expect(saveNow).toHaveBeenCalledTimes(1);
      expect(prevented).toBe(true); // event.preventDefault() was honored
      expect(event.defaultPrevented).toBe(true);
    },
  );
});
