/**
 * "Do it again" lifecycle tests for the compile trigger: a second compile replaces the first
 * result, a failed compile keeps the last good PDF, and the page can compile again after an
 * error. The compile always targets the project's main file (the client does not pick one),
 * so there is no "compile after switching main document" case to cover here.
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { requestCompile } from "../api";
import type { CompileJobStatus, CompileStatus } from "../types";
import { useCompile } from "./useCompile";

vi.mock("../api", () => ({
  requestCompile: vi.fn(),
  getCompile: vi.fn(),
  cancelCompile: vi.fn(),
  compileEventsUrl: vi.fn(() => "http://x/events?access_token=t"),
}));

const reqCompile = requestCompile as Mock;

function snap(id: string, status: CompileJobStatus, over: Partial<CompileStatus> = {}): CompileStatus {
  return {
    id,
    project_id: "p1",
    status,
    main_file: "main.tex",
    has_pdf: false,
    created_at: "2026-06-09T00:00:00Z",
    started_at: null,
    finished_at: null,
    duration_ms: null,
    exit_code: null,
    error_message: null,
    log_excerpt: null,
    artifact_manifest: null,
    ...over,
  };
}

beforeEach(() => {
  reqCompile.mockReset();
});
afterEach(() => vi.clearAllMocks());

describe("useCompile, do it again", () => {
  it("a second compile replaces the first result", async () => {
    reqCompile.mockResolvedValueOnce(snap("c1", "success", { has_pdf: true }));
    const { result } = renderHook(() => useCompile("p1"));

    act(() => result.current.compile());
    await waitFor(() => expect(result.current.lastSuccessId).toBe("c1"));

    reqCompile.mockResolvedValueOnce(snap("c2", "success", { has_pdf: true }));
    act(() => result.current.compile());
    await waitFor(() => expect(result.current.compileId).toBe("c2"));
    expect(result.current.lastSuccessId).toBe("c2");
    expect(result.current.status).toBe("success");
    expect(result.current.progressLabel).toBeNull();
    expect(reqCompile).toHaveBeenCalledTimes(2);
  });

  it("keeps the last good PDF through a failed compile, then recovers", async () => {
    reqCompile.mockResolvedValueOnce(snap("c1", "success", { has_pdf: true }));
    const { result } = renderHook(() => useCompile("p1"));
    act(() => result.current.compile());
    await waitFor(() => expect(result.current.lastSuccessId).toBe("c1"));

    reqCompile.mockResolvedValueOnce(
      snap("c2", "failure", { error_message: "! Undefined control sequence." }),
    );
    act(() => result.current.compile());
    await waitFor(() => expect(result.current.status).toBe("failure"));
    expect(result.current.error).toBe("! Undefined control sequence.");
    expect(result.current.lastSuccessId).toBe("c1");

    reqCompile.mockResolvedValueOnce(snap("c3", "success", { has_pdf: true }));
    act(() => result.current.compile());
    await waitFor(() => expect(result.current.lastSuccessId).toBe("c3"));
    expect(result.current.error).toBeNull();
  });

  it("starts again after a system error, which clears its own busy state", async () => {
    reqCompile.mockRejectedValueOnce(new Error("network down"));
    const { result } = renderHook(() => useCompile("p1"));
    act(() => result.current.compile());
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("network down");

    reqCompile.mockResolvedValueOnce(snap("c4", "success", { has_pdf: true }));
    act(() => result.current.compile());
    await waitFor(() => expect(result.current.lastSuccessId).toBe("c4"));
    expect(reqCompile).toHaveBeenCalledTimes(2);
  });

  it("ignores a compile asked for while one is still in flight", async () => {
    let finish: (s: CompileStatus) => void = () => {};
    reqCompile.mockReturnValueOnce(new Promise<CompileStatus>((resolve) => (finish = resolve)));
    const { result } = renderHook(() => useCompile("p1"));
    act(() => result.current.compile());
    await waitFor(() => expect(reqCompile).toHaveBeenCalledTimes(1));
    act(() => result.current.compile());
    await new Promise((r) => setTimeout(r, 10));
    expect(reqCompile).toHaveBeenCalledTimes(1);

    await act(async () => finish(snap("c1", "success", { has_pdf: true })));
    await waitFor(() => expect(result.current.lastSuccessId).toBe("c1"));
  });
});
