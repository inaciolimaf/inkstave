import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import { ApiError, apiClient } from "@/lib/api-client";

import { getProblems } from "./problems";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return { ...actual, apiClient: { ...actual.apiClient, get: vi.fn() } };
});

const get = apiClient.get as Mock;
afterEach(() => get.mockReset());

const PAYLOAD = { compile_id: "c1", errors: 1, warnings: 0, infos: 0, problems: [] };

describe("getProblems", () => {
  it("fetches problems for a compile id", async () => {
    get.mockResolvedValue(PAYLOAD);
    const result = await getProblems("p1", "c1");
    expect(result).toEqual({ ok: true, value: PAYLOAD });
    expect(get).toHaveBeenCalledWith("/api/v1/projects/p1/compiles/c1/problems");
  });

  it("supports the 'latest' alias", async () => {
    get.mockResolvedValue(PAYLOAD);
    await getProblems("p1", "latest");
    expect(get).toHaveBeenCalledWith("/api/v1/projects/p1/compiles/latest/problems");
  });

  it("maps a 404 to log_unavailable", async () => {
    get.mockRejectedValue(new ApiError(404, "log_unavailable"));
    expect(await getProblems("p1", "c1")).toEqual({ ok: false, reason: "log_unavailable" });
  });

  it("maps other failures to error", async () => {
    get.mockRejectedValue(new ApiError(500, "boom"));
    expect(await getProblems("p1", "c1")).toEqual({ ok: false, reason: "error" });
  });
});
