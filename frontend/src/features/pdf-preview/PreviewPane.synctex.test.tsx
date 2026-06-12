import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { PreviewPane } from "./PreviewPane";
import { getCompilePdf, requestCompile } from "./api";
import { loadPdfDocument } from "./pdfjs";
import { pdfToCode } from "./synctex";
import type { PdfHighlight } from "./hooks/useSyncTex";
import type { PageClickHandler } from "./PdfViewer";
import type { CompileJobStatus, CompileStatus } from "./types";

vi.mock("./api", () => ({
  requestCompile: vi.fn(),
  getCompile: vi.fn(),
  cancelCompile: vi.fn(),
  getCompileLog: vi.fn(),
  getCompilePdf: vi.fn(),
  compileEventsUrl: vi.fn(() => "http://x/events"),
}));
vi.mock("./pdfjs", () => ({ loadPdfDocument: vi.fn() }));
vi.mock("./synctex", () => ({ pdfToCode: vi.fn() }));

const reqCompile = requestCompile as Mock;
const load = loadPdfDocument as Mock;
const inverseSync = pdfToCode as Mock;

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

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  sources.length = 0;
  reqCompile.mockReset();
  load.mockReset();
  inverseSync.mockReset();
});
afterEach(() => vi.unstubAllGlobals());

const BOX = { page: 2, h: 10, v: 20, width: 30, height: 5, depth: 2 };

describe("PreviewPane forward sync", () => {
  it("jumps to the target page and shows a highlight overlay", async () => {
    reqCompile.mockResolvedValue(snap("queued"));
    (getCompilePdf as Mock).mockResolvedValue(new ArrayBuffer(8));
    load.mockResolvedValue(fakeDoc(2));

    const { rerender } = render(<PreviewPane projectId="p1" syncTarget={null} />);
    await userEvent.click(screen.getByRole("button", { name: "Compile project" }));
    await waitFor(() => expect(sources).toHaveLength(1));
    await act(async () => {
      sources[0].emit("status", snap("success", { has_pdf: true }));
      await Promise.resolve();
    });
    await waitFor(() => expect(screen.getByText("of 2")).toBeInTheDocument());

    const target: PdfHighlight = { page: 2, box: BOX, nonce: 1 };
    rerender(<PreviewPane projectId="p1" syncTarget={target} />);

    await waitFor(() => expect(screen.getByTestId("sync-highlight")).toBeInTheDocument());
    expect(screen.getByLabelText("Page number")).toHaveValue("2");
  });
});

describe("PreviewPane inverse sync (PDF -> editor)", () => {
  it("calls pdfToCode on a page click and reveals + highlights the returned line", async () => {
    reqCompile.mockResolvedValue(snap("queued"));
    (getCompilePdf as Mock).mockResolvedValue(new ArrayBuffer(8));
    load.mockResolvedValue(fakeDoc(1));
    // Synctex inverse API resolves the clicked PDF point to a source line.
    inverseSync.mockResolvedValue({ ok: true, value: { file: "main.tex", line: 42, column: null } });

    // Mirror editor-workspace.handlePdfClick: resolve the point via pdfToCode,
    // then reveal the editor line and flash a highlight decoration.
    const revealLine = vi.fn();
    const highlightLine = vi.fn();
    const handlePdfClick: PageClickHandler = async (page, h, v) => {
      const result = await pdfToCode("p1", { page, h, v });
      if (result.ok) {
        revealLine(result.value.line);
        highlightLine(result.value.line);
      }
    };

    render(<PreviewPane projectId="p1" syncTarget={null} onPdfClick={handlePdfClick} />);
    await userEvent.click(screen.getByRole("button", { name: "Compile project" }));
    await waitFor(() => expect(sources).toHaveLength(1));
    await act(async () => {
      sources[0].emit("status", snap("success", { has_pdf: true }));
      await Promise.resolve();
    });
    await waitFor(() => expect(screen.getByLabelText("Page 1")).toBeInTheDocument());

    // Double-click the page; PdfViewer converts CSS offsets to PDF points by
    // dividing by the active scale (PreviewPane's default scale is 1).
    fireEvent.doubleClick(screen.getByLabelText("Page 1"), { clientX: 120, clientY: 80 });

    await waitFor(() => expect(inverseSync).toHaveBeenCalled());
    // The inverse API is queried with the click's PDF-point coordinates.
    expect(inverseSync).toHaveBeenCalledWith("p1", { page: 1, h: 120, v: 80 });
    // The editor then scrolls/reveals to the resolved line with a highlight.
    await waitFor(() => expect(revealLine).toHaveBeenCalledWith(42));
    expect(highlightLine).toHaveBeenCalledWith(42);
  });
});
