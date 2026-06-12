import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { PreviewPane } from "./PreviewPane";
import { cancelCompile, getCompileLog, getCompilePdf, requestCompile } from "./api";
import { loadPdfDocument } from "./pdfjs";
import type { CompileJobStatus, CompileStatus } from "./types";

vi.mock("./api", () => ({
  requestCompile: vi.fn(),
  getCompile: vi.fn(),
  cancelCompile: vi.fn(),
  getCompileLog: vi.fn(),
  getCompilePdf: vi.fn(),
  compileEventsUrl: vi.fn(() => "http://x/events?access_token=t"),
}));
vi.mock("./pdfjs", () => ({ loadPdfDocument: vi.fn() }));

const reqCompile = requestCompile as Mock;
const cancelC = cancelCompile as Mock;
const getLog = getCompileLog as Mock;
const getPdf = getCompilePdf as Mock;
const load = loadPdfDocument as Mock;

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

function fakePage() {
  return {
    getViewport: ({ scale }: { scale: number }) => ({ width: 120 * scale, height: 160 * scale }),
    render: () => ({ promise: Promise.resolve(), cancel: () => {} }),
  };
}
function fakeDoc(numPages: number) {
  return {
    numPages,
    destroy: vi.fn().mockResolvedValue(undefined),
    getPage: vi.fn().mockResolvedValue(fakePage()),
  };
}

interface Listener {
  (e: { data: string }): void;
}
const sources: FakeEventSource[] = [];
class FakeEventSource {
  listeners: Record<string, Listener[]> = {};
  onerror: ((e: unknown) => void) | null = null;
  constructor(public url: string) {
    sources.push(this);
  }
  addEventListener(type: string, cb: Listener) {
    (this.listeners[type] ??= []).push(cb);
  }
  emit(type: string, data: unknown) {
    for (const cb of this.listeners[type] ?? []) cb({ data: JSON.stringify(data) });
  }
  close() {}
}

async function emitStatus(data: CompileStatus) {
  await act(async () => {
    sources[sources.length - 1].emit("status", data);
    await Promise.resolve();
  });
}

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  sources.length = 0;
  reqCompile.mockReset();
  cancelC.mockReset();
  getLog.mockReset();
  getPdf.mockReset();
  load.mockReset();
});
afterEach(() => vi.unstubAllGlobals());

describe("PreviewPane (integration)", () => {
  it("compiles, renders the PDF, and drives zoom + page navigation", async () => {
    reqCompile.mockResolvedValue(snap("queued"));
    getPdf.mockResolvedValue(new ArrayBuffer(8));
    load.mockResolvedValue(fakeDoc(2));

    render(<PreviewPane projectId="p1" />);
    expect(screen.getByText(/compile to see a preview/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Compile project" }));
    await waitFor(() => expect(sources).toHaveLength(1));
    expect(reqCompile).toHaveBeenCalledTimes(1);

    await emitStatus(snap("running"));
    expect(screen.getByRole("status")).toHaveTextContent("Compiling…");

    await emitStatus(snap("success", { has_pdf: true, duration_ms: 1500 }));

    // PDF loads and the toolbar appears.
    await waitFor(() => expect(screen.getByText("of 2")).toBeInTheDocument());
    expect(getPdf).toHaveBeenCalledWith("p1", "c1");
    expect(screen.getByRole("status")).toHaveTextContent("Compilation succeeded.");

    // Zoom.
    expect(screen.getByLabelText("Zoom level")).toHaveTextContent("100%");
    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(screen.getByLabelText("Zoom level")).toHaveTextContent("120%");

    // Page navigation.
    expect(screen.getByLabelText("Page number")).toHaveValue("1");
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByLabelText("Page number")).toHaveValue("2");
  });

  it("debounces: a second Compile click does not fire a second POST", async () => {
    reqCompile.mockResolvedValue(snap("queued"));
    render(<PreviewPane projectId="p1" />);
    await userEvent.click(screen.getByRole("button", { name: "Compile project" }));
    await waitFor(() => expect(sources).toHaveLength(1));
    // While active the Compile button is gone (replaced by Compiling/Cancel).
    expect(screen.queryByRole("button", { name: "Compile project" })).toBeNull();
    expect(reqCompile).toHaveBeenCalledTimes(1);
  });

  it("cancels an active compile", async () => {
    reqCompile.mockResolvedValue(snap("queued"));
    cancelC.mockResolvedValue(snap("cancelled"));
    render(<PreviewPane projectId="p1" />);
    await userEvent.click(screen.getByRole("button", { name: "Compile project" }));
    await waitFor(() => expect(sources).toHaveLength(1));
    await userEvent.click(screen.getByRole("button", { name: "Cancel compilation" }));
    expect(cancelC).toHaveBeenCalledWith("p1", "c1");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Compile project" })).toBeInTheDocument(),
    );
  });

  it("shows the error state and auto-expands the raw log on failure", async () => {
    reqCompile.mockResolvedValue(snap("queued"));
    getLog.mockResolvedValue("! LaTeX Error: \\foo undefined.");
    render(<PreviewPane projectId="p1" />);

    await userEvent.click(screen.getByRole("button", { name: "Compile project" }));
    await waitFor(() => expect(sources).toHaveLength(1));
    await emitStatus(snap("failure"));

    expect(screen.getByRole("alert")).toHaveTextContent("Compilation failed");
    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Compile log" })).toHaveTextContent(
        "! LaTeX Error: \\foo undefined.",
      ),
    );
    expect(getLog).toHaveBeenCalledWith("p1", "c1");
  });

  it("shows a timeout-specific message and re-triggers via Try again", async () => {
    reqCompile.mockResolvedValue(snap("queued"));
    getLog.mockResolvedValue("timed out");
    render(<PreviewPane projectId="p1" />);

    await userEvent.click(screen.getByRole("button", { name: "Compile project" }));
    await waitFor(() => expect(sources).toHaveLength(1));
    await emitStatus(snap("timeout"));

    expect(screen.getByRole("alert")).toHaveTextContent("Compilation timed out");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(reqCompile).toHaveBeenCalledTimes(2);
  });
});
