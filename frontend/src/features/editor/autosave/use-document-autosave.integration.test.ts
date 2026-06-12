/**
 * HTTP-boundary integration test for the autosave flow (spec 19 §8).
 *
 * Unlike `use-document-autosave.test.ts` (which function-mocks `saveDocument`),
 * this test runs the *real* API-client code path and stubs only the HTTP
 * boundary via `vi.stubGlobal('fetch', ...)` — the same fetch-stub harness used
 * elsewhere in the frontend tests (no MSW, no new dependency). This verifies the
 * request path/body/version handling that the function-level mock bypasses.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { tokenStore } from "@/lib/token-store";

import { useDocumentAutosave } from "./use-document-autosave";

interface MockResponse {
  ok: boolean;
  status: number;
  statusText: string;
  json: () => Promise<unknown>;
  text: () => Promise<string>;
}

function mockResponse(status: number, body?: unknown): MockResponse {
  const text = body === undefined ? "" : JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => JSON.parse(text),
    text: async () => text,
  };
}

let fetchMock: Mock;

const LOADED = { id: "d1", content: "hello", version: 5 };

beforeEach(() => {
  vi.useFakeTimers();
  tokenStore.clear();
  localStorage.clear();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function setup() {
  return renderHook(() => useDocumentAutosave("p", LOADED));
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function lastRequest() {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1] as [
    string,
    RequestInit,
  ];
  return { url, init, body: JSON.parse(String(init.body)) as Record<string, unknown> };
}

describe("useDocumentAutosave (HTTP boundary)", () => {
  it("PUTs the replace-content endpoint with { content, base_version } and advances on success", async () => {
    // Real api-client → fetch. Wire response carries the new version.
    fetchMock.mockResolvedValue(
      mockResponse(200, {
        entity_id: "d1",
        project_id: "p",
        version: 6,
        size_bytes: 11,
        content: "hello world",
        updated_at: "2026-01-01T00:00:00Z",
      }),
    );
    const { result } = setup();

    act(() => result.current.onLocalChange("hello world"));
    await advance(1000);

    const first = lastRequest();
    expect(first.url).toContain("/api/v1/projects/p/documents/d1");
    expect(first.init.method).toBe("PUT");
    expect(first.body).toEqual({ content: "hello world", base_version: 5 });
    expect(result.current.status).toBe("clean");

    // The next save uses the *advanced* server version (6, not 5).
    fetchMock.mockResolvedValue(
      mockResponse(200, {
        entity_id: "d1",
        project_id: "p",
        version: 7,
        size_bytes: 5,
        content: "again",
        updated_at: "2026-01-01T00:00:01Z",
      }),
    );
    act(() => result.current.onLocalChange("again"));
    await advance(1000);

    const second = lastRequest();
    expect(second.body).toEqual({ content: "again", base_version: 6 });
    expect(result.current.status).toBe("clean");
  });

  it("resolves the conflict flow when the server replies 409", async () => {
    // A 409 with the envelope's `error.details[0]` carrying the server state.
    fetchMock.mockResolvedValueOnce(
      mockResponse(409, {
        error: {
          type: "version_conflict",
          message: "version_conflict",
          details: [{ current_version: 9, current_content: "server text" }],
        },
      }),
    );
    const { result } = setup();

    act(() => result.current.onLocalChange("mine"));
    await advance(1000);

    expect(result.current.status).toBe("conflict");
    expect(result.current.conflict).toEqual({
      currentVersion: 9,
      currentContent: "server text",
    });

    // Resolve by reloading the server copy → back to a clean, non-conflicting state.
    act(() => result.current.resolveReload());
    expect(result.current.status).toBe("clean");
    expect(result.current.displayText).toBe("server text");
    expect(result.current.conflict).toBeNull();
  });
});
