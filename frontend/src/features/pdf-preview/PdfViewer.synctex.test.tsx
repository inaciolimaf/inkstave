import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PdfViewer } from "./PdfViewer";
import type { PdfViewport } from "./hooks/usePdfViewport";

function fakePage(render = vi.fn(() => ({ promise: Promise.resolve(), cancel: () => {} }))) {
  return {
    getViewport: ({ scale }: { scale: number }) => ({ width: 120 * scale, height: 160 * scale }),
    render,
  };
}
function fakeDoc(numPages: number, page = fakePage()) {
  return {
    numPages,
    destroy: vi.fn(),
    getPage: vi.fn().mockResolvedValue(page),
  } as unknown as Parameters<typeof PdfViewer>[0]["pdf"];
}

function viewport(over: Partial<PdfViewport> = {}): PdfViewport {
  return {
    scale: 2,
    fitMode: "none",
    page: 1,
    numPages: 1,
    zoomPercent: 200,
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
    fitWidth: vi.fn(),
    fitPage: vi.fn(),
    setScale: vi.fn(),
    setPage: vi.fn(),
    goPrev: vi.fn(),
    goNext: vi.fn(),
    jumpTo: vi.fn(),
    ...over,
  };
}

describe("PdfViewer SyncTeX", () => {
  it("converts a double-click to PDF points and reports the page", () => {
    const onPageClick = vi.fn();
    render(<PdfViewer pdf={fakeDoc(1)} viewport={viewport()} onPageClick={onPageClick} />);
    const page = screen.getByLabelText("Page 1");
    // jsdom getBoundingClientRect is the origin, so clientX/clientY are the offsets.
    fireEvent.doubleClick(page, { clientX: 120, clientY: 80 });
    expect(onPageClick).toHaveBeenCalledWith(1, 60, 40); // /scale=2
  });

  it("renders a transient highlight overlay for the targeted page", () => {
    const box = { page: 1, h: 10, v: 20, width: 30, height: 5, depth: 2 };
    render(<PdfViewer pdf={fakeDoc(1)} viewport={viewport()} highlight={{ page: 1, box }} />);
    expect(screen.getByTestId("sync-highlight")).toBeInTheDocument();
  });

  it("re-renders the document when the zoom (scale) changes", async () => {
    const doc = fakeDoc(1);
    const getPage = (doc as unknown as { getPage: ReturnType<typeof vi.fn> }).getPage;

    const { rerender } = render(<PdfViewer pdf={doc} viewport={viewport({ scale: 1 })} />);
    await waitFor(() => expect(getPage).toHaveBeenCalled());
    const callsAtScale1 = getPage.mock.calls.length;

    // Changing the scale must re-run the page render effect (deps include scale).
    rerender(<PdfViewer pdf={doc} viewport={viewport({ scale: 2, zoomPercent: 200 })} />);
    await waitFor(() => expect(getPage.mock.calls.length).toBeGreaterThan(callsAtScale1));
  });

  it("does not render an overlay on a non-targeted page", () => {
    const box = { page: 2, h: 10, v: 20, width: 30, height: 5, depth: 2 };
    render(
      <PdfViewer
        pdf={fakeDoc(1)}
        viewport={viewport({ numPages: 1 })}
        highlight={{ page: 2, box }}
      />,
    );
    expect(screen.queryByTestId("sync-highlight")).toBeNull();
  });
});
