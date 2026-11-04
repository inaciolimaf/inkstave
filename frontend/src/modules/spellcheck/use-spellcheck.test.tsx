import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { type MockInstance, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getProject } from "@/modules/projects";

import { listDictionary } from "./api";
import { useSpellcheck } from "./use-spellcheck";

vi.mock("@/modules/projects", () => ({
  getProject: vi.fn(),
  projectKey: (id: string) => ["projects", id],
}));

vi.mock("./api", () => ({
  listDictionary: vi.fn(async () => ["inkstave"]),
  addDictionaryWord: vi.fn(),
  removeDictionaryWord: vi.fn(),
  updateSpellcheckLanguage: vi.fn(),
}));

function wrapperFor(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function projectWith(language: string) {
  vi.mocked(getProject).mockResolvedValue({ id: "p1", spellcheckLanguage: language } as never);
}

describe("useSpellcheck", () => {
  let fetchSpy: MockInstance<typeof fetch>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, "fetch");
    vi.mocked(listDictionary).mockClear();
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("loads nothing and binds nothing while the language is off", async () => {
    projectWith("off");
    const client = new QueryClient();
    const { result } = renderHook(() => useSpellcheck("p1", "doc1"), { wrapper: wrapperFor(client) });

    // Let the project query settle, so the hook has read the language before the assertions.
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
    expect(result.current.binding).toBeNull();
    expect(listDictionary).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("binds the language and the personal dictionary once both are loaded", async () => {
    projectWith("pt-BR");
    const client = new QueryClient();
    const { result } = renderHook(() => useSpellcheck("p1", "doc1"), { wrapper: wrapperFor(client) });

    await waitFor(() => expect(result.current.binding).not.toBeNull());
    expect(result.current.binding?.language).toBe("pt-BR");
    expect(result.current.binding?.accepts("Inkstave")).toBe(true);
    expect(result.current.binding?.accepts("metodolgia")).toBe(false);
    expect(result.current.failed).toBe(false);
  });
});
