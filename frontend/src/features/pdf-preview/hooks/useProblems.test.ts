import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import { getProblems } from "../problems";
import { useProblems } from "./useProblems";

vi.mock("../problems", () => ({ getProblems: vi.fn() }));
const get = getProblems as Mock;
const PAYLOAD = { compile_id: "c1", errors: 1, warnings: 0, infos: 0, problems: [] };

afterEach(() => get.mockReset());

describe("useProblems", () => {
  it("loads problems for the compile key", async () => {
    get.mockResolvedValue({ ok: true, value: PAYLOAD });
    const { result } = renderHook(() => useProblems("p1", "c1"));
    await waitFor(() => expect(result.current.problems).toEqual(PAYLOAD));
    expect(get).toHaveBeenCalledWith("p1", "c1");
  });

  it("surfaces the log_unavailable reason", async () => {
    get.mockResolvedValue({ ok: false, reason: "log_unavailable" });
    const { result } = renderHook(() => useProblems("p1", "latest"));
    await waitFor(() => expect(result.current.reason).toBe("log_unavailable"));
    expect(result.current.problems).toBeNull();
  });

  it("does nothing without a key", () => {
    renderHook(() => useProblems("p1", null));
    expect(get).not.toHaveBeenCalled();
  });
});
