import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import { ApiError, apiClient } from "@/lib/api-client";

import { codeToPdf, pdfToCode, reasonFromError } from "./synctex";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return { ...actual, apiClient: { ...actual.apiClient, get: vi.fn() } };
});

const get = apiClient.get as Mock;

afterEach(() => get.mockReset());

describe("codeToPdf", () => {
  it("builds the forward URL and returns boxes on success", async () => {
    get.mockResolvedValue({ boxes: [{ page: 1, h: 100, v: 200, width: 4, height: 1, depth: 0 }] });
    const result = await codeToPdf("p1", { file: "main.tex", line: 10, compileId: "c1" });
    expect(result).toEqual({ ok: true, value: { boxes: [expect.objectContaining({ page: 1 })] } });
    const url = get.mock.calls[0][0] as string;
    expect(url).toContain("/api/v1/projects/p1/synctex/code-to-pdf?");
    expect(url).toContain("file=main.tex");
    expect(url).toContain("line=10");
    expect(url).toContain("compile_id=c1");
  });

  it("maps a synctex_unavailable 404 to its reason", async () => {
    get.mockRejectedValue(new ApiError(404, "synctex_unavailable"));
    expect(await codeToPdf("p1", { file: "main.tex", line: 1 })).toEqual({
      ok: false,
      reason: "synctex_unavailable",
    });
  });

  it("maps a no_match 404 to its reason", async () => {
    get.mockRejectedValue(new ApiError(404, "no_match"));
    expect(await codeToPdf("p1", { file: "x.tex", line: 1 })).toEqual({
      ok: false,
      reason: "no_match",
    });
  });
});

describe("pdfToCode", () => {
  it("builds the inverse URL and returns the location", async () => {
    get.mockResolvedValue({ file: "main.tex", line: 10, column: null });
    const result = await pdfToCode("p1", { page: 1, h: 100, v: 200 });
    expect(result).toEqual({ ok: true, value: { file: "main.tex", line: 10, column: null } });
    const url = get.mock.calls[0][0] as string;
    expect(url).toContain("/synctex/pdf-to-code?");
    expect(url).toContain("page=1");
    expect(url).toContain("h=100");
    expect(url).toContain("v=200");
  });

  it("returns an error reason for a non-404 failure", async () => {
    get.mockRejectedValue(new ApiError(500, "boom"));
    expect(await pdfToCode("p1", { page: 1, h: 1, v: 1 })).toEqual({ ok: false, reason: "error" });
  });
});

describe("reasonFromError", () => {
  it("classifies the discriminants", () => {
    expect(reasonFromError(new ApiError(404, "synctex_unavailable"))).toBe("synctex_unavailable");
    expect(reasonFromError(new ApiError(404, "no_match"))).toBe("no_match");
    expect(reasonFromError(new ApiError(403, "x"))).toBe("error");
    expect(reasonFromError(new Error("network"))).toBe("error");
  });
});
