import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api-client";
import { tokenStore } from "@/lib/token-store";

import { getDiff, listLabels } from "./api";

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

function setFetch(impl: (url: string, init: RequestInit) => Promise<MockResponse>) {
  const fn = vi.fn(impl);
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => {
  tokenStore.clear();
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getDiff", () => {
  it("maps a normal 200 diff body to a DiffResult (AC1)", async () => {
    setFetch(async () =>
      mockResponse(200, {
        from: 1,
        to: "current",
        binary: false,
        too_large: false,
        hunks: [
          {
            old_start: 1,
            old_lines: 1,
            new_start: 1,
            new_lines: 1,
            segments: [{ type: "added", value: "hi\n" }],
          },
        ],
      }),
    );
    const result = await getDiff("p1", "d1", 1, "current");
    expect(result).toEqual({
      from: 1,
      to: "current",
      binary: false,
      tooLarge: false,
      hunks: [
        {
          oldStart: 1,
          oldLines: 1,
          newStart: 1,
          newLines: 1,
          segments: [{ type: "added", value: "hi\n" }],
        },
      ],
    });
  });

  it("maps a 413 'too large' response to tooLarge without throwing (AC2)", async () => {
    setFetch(async () =>
      mockResponse(413, { from: 2, to: 5, binary: false, too_large: true, hunks: [] }),
    );
    const result = await getDiff("p1", "d1", 2, 5);
    expect(result.tooLarge).toBe(true);
    expect(result.binary).toBe(false);
    expect(result.hunks).toHaveLength(0);
    expect(result.from).toBe(2);
    expect(result.to).toBe(5);
  });

  it("still throws an ApiError on a non-413 error (AC3)", async () => {
    setFetch(async () => mockResponse(403, { error: { type: "forbidden", message: "nope" } }));
    await expect(getDiff("p1", "d1", 1, "current")).rejects.toBeInstanceOf(ApiError);
  });

  it("still throws an ApiError on a 500 (AC3)", async () => {
    setFetch(async () => mockResponse(500, { error: { type: "internal", message: "boom" } }));
    await expect(getDiff("p1", "d1", 1, "current")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("listLabels", () => {
  it("GETs /history/labels and maps each wire item via toLabel", async () => {
    const fetchMock = setFetch(async () =>
      mockResponse(200, [
        {
          id: "l1",
          name: "v1.0",
          version: 3,
          doc_id: "d1",
          created_by: "u1",
          created_at: "2026-01-01T00:00:00Z",
        },
        {
          id: "l2",
          name: "draft",
          version: 5,
          doc_id: null,
          created_by: null,
          created_at: "2026-02-02T00:00:00Z",
        },
      ]),
    );
    const labels = await listLabels("p1", "d1");
    expect(fetchMock.mock.calls[0][0]).toContain("/api/v1/projects/p1/docs/d1/history/labels");
    expect(labels).toEqual([
      {
        id: "l1",
        name: "v1.0",
        version: 3,
        docId: "d1",
        createdBy: "u1",
        createdAt: "2026-01-01T00:00:00Z",
      },
      {
        id: "l2",
        name: "draft",
        version: 5,
        docId: null,
        createdBy: null,
        createdAt: "2026-02-02T00:00:00Z",
      },
    ]);
  });
});
