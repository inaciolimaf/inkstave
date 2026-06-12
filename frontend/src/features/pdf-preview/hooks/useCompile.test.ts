import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { cancelCompile, getCompile, requestCompile } from "../api";
import type { CompileJobStatus, CompileStatus } from "../types";
import { useCompile } from "./useCompile";

vi.mock("../api", () => ({
  requestCompile: vi.fn(),
  getCompile: vi.fn(),
  cancelCompile: vi.fn(),
  compileEventsUrl: vi.fn(() => "http://x/events?access_token=t"),
}));

const reqCompile = requestCompile as Mock;
const getC = getCompile as Mock;
const cancelC = cancelCompile as Mock;

function snap(status: CompileJobStatus, over: Partial<CompileStatus> = {}): CompileStatus {
  return {
    id: "c1",
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

interface Listener {
  (e: { data: string }): void;
}

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  listeners: Record<string, Listener[]> = {};
  onerror: ((e: unknown) => void) | null = null;
  closed = false;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, cb: Listener) {
    (this.listeners[type] ??= []).push(cb);
  }
  emit(type: string, data: unknown) {
    for (const cb of this.listeners[type] ?? []) cb({ data: JSON.stringify(data) });
  }
  triggerError() {
    this.onerror?.({});
  }
  close() {
    this.closed = true;
  }
  static last() {
    return this.instances[this.instances.length - 1];
  }
}

beforeEach(() => {
  reqCompile.mockReset();
  getC.mockReset();
  cancelC.mockReset();
  FakeEventSource.instances = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("useCompile (SSE)", () => {
  beforeEach(() => vi.stubGlobal("EventSource", FakeEventSource));

  it("runs idle → queued → running → success and records lastSuccessId", async () => {
    reqCompile.mockResolvedValue(snap("queued"));
    const { result } = renderHook(() => useCompile("p1"));
    expect(result.current.status).toBe("idle");

    await act(async () => {
      result.current.compile();
    });
    expect(reqCompile).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe("queued");
    expect(result.current.compileId).toBe("c1");
    expect(result.current.progressLabel).toBe("Queued…");

    const es = FakeEventSource.last();
    act(() => es.emit("status", snap("running")));
    expect(result.current.status).toBe("running");
    expect(result.current.progressLabel).toBe("Compiling…");

    act(() => es.emit("status", snap("success", { has_pdf: true, duration_ms: 1200 })));
    expect(result.current.status).toBe("success");
    expect(result.current.lastSuccessId).toBe("c1");
    expect(result.current.progressLabel).toBeNull();
    expect(es.closed).toBe(true);
  });

  it("surfaces a failure outcome via the stream", async () => {
    reqCompile.mockResolvedValue(snap("queued"));
    const { result } = renderHook(() => useCompile("p1"));
    await act(async () => {
      result.current.compile();
    });
    act(() => FakeEventSource.last().emit("status", snap("failure")));
    expect(result.current.status).toBe("failure");
    expect(result.current.lastSuccessId).toBeNull();
  });

  it("debounces a rapid second compile (no second POST)", async () => {
    reqCompile.mockResolvedValue(snap("queued"));
    const { result } = renderHook(() => useCompile("p1"));
    await act(async () => {
      result.current.compile();
      result.current.compile();
    });
    expect(reqCompile).toHaveBeenCalledTimes(1);
  });

  it("cancels an active compile and returns to a cancelled state", async () => {
    reqCompile.mockResolvedValue(snap("queued"));
    cancelC.mockResolvedValue(snap("cancelled"));
    const { result } = renderHook(() => useCompile("p1"));
    await act(async () => {
      result.current.compile();
    });
    await act(async () => {
      result.current.cancel();
    });
    expect(cancelC).toHaveBeenCalledWith("p1", "c1");
    expect(result.current.status).toBe("cancelled");
  });

  it("re-enables compiling after a terminal status", async () => {
    reqCompile.mockResolvedValueOnce(snap("queued"));
    const { result } = renderHook(() => useCompile("p1"));
    await act(async () => {
      result.current.compile();
    });
    act(() => FakeEventSource.last().emit("status", snap("failure")));

    reqCompile.mockResolvedValueOnce(snap("queued", { id: "c2" }));
    await act(async () => {
      result.current.compile();
    });
    expect(reqCompile).toHaveBeenCalledTimes(2);
    expect(result.current.compileId).toBe("c2");
  });

  it("reports a system error if the POST fails", async () => {
    reqCompile.mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useCompile("p1"));
    await act(async () => {
      result.current.compile();
    });
    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe("boom");
  });

  it("closes the SSE subscription on unmount (no leak)", async () => {
    reqCompile.mockResolvedValue(snap("queued"));
    const { result, unmount } = renderHook(() => useCompile("p1"));
    await act(async () => {
      result.current.compile();
    });
    const es = FakeEventSource.last();
    expect(es.closed).toBe(false);
    act(() => unmount());
    expect(es.closed).toBe(true);
  });
});

describe("useCompile (polling fallback)", () => {
  it("falls back to polling when EventSource is unavailable", async () => {
    vi.stubGlobal("EventSource", undefined);
    vi.useFakeTimers();
    reqCompile.mockResolvedValue(snap("queued"));
    getC.mockResolvedValue(snap("success", { has_pdf: true }));

    const { result } = renderHook(() => useCompile("p1"));
    await act(async () => {
      result.current.compile();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.status).toBe("queued");
    expect(getC).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(getC).toHaveBeenCalledWith("p1", "c1");
    expect(result.current.status).toBe("success");
  });

  it("falls back to polling when the SSE stream errors", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.useFakeTimers();
    reqCompile.mockResolvedValue(snap("queued"));
    getC.mockResolvedValue(snap("success", { has_pdf: true }));

    const { result } = renderHook(() => useCompile("p1"));
    await act(async () => {
      result.current.compile();
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => FakeEventSource.last().triggerError());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(getC).toHaveBeenCalledWith("p1", "c1");
    expect(result.current.status).toBe("success");
  });
});
