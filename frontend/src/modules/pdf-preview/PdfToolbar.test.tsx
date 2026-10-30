import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PdfToolbar } from "./PdfToolbar";
import type { PdfViewport } from "./hooks/usePdfViewport";

function makeViewport(over: Partial<PdfViewport> = {}): PdfViewport {
  return {
    scale: 1,
    fitMode: "width",
    page: 2,
    numPages: 5,
    zoomPercent: 100,
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

describe("PdfToolbar", () => {
  it("wires zoom and fit controls with accessible labels", async () => {
    const vp = makeViewport();
    render(<PdfToolbar viewport={vp} />);

    expect(screen.getByLabelText("Zoom level")).toHaveTextContent("100%");
    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    await userEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    await userEvent.click(screen.getByRole("button", { name: "Fit width" }));
    await userEvent.click(screen.getByRole("button", { name: "Fit page" }));
    expect(vp.zoomIn).toHaveBeenCalled();
    expect(vp.zoomOut).toHaveBeenCalled();
    expect(vp.fitWidth).toHaveBeenCalled();
    expect(vp.fitPage).toHaveBeenCalled();
  });

  it("navigates pages and shows the page indicator", async () => {
    const vp = makeViewport();
    render(<PdfToolbar viewport={vp} />);

    expect(screen.getByText("of 5")).toBeInTheDocument();
    expect(screen.getByLabelText("Page number")).toHaveValue("2");

    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(vp.goNext).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(vp.goPrev).toHaveBeenCalled();
  });

  it("jumps to a typed page on submit", async () => {
    const vp = makeViewport();
    render(<PdfToolbar viewport={vp} />);
    const input = screen.getByLabelText("Page number");
    await userEvent.clear(input);
    await userEvent.type(input, "4{enter}");
    expect(vp.jumpTo).toHaveBeenCalledWith(4);
  });

  it("disables Previous on the first page", () => {
    render(<PdfToolbar viewport={makeViewport({ page: 1 })} />);
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
  });

  it("renders a Download control when given a handler", async () => {
    const onDownload = vi.fn();
    render(<PdfToolbar viewport={makeViewport()} onDownload={onDownload} />);
    await userEvent.click(screen.getByRole("button", { name: "Download PDF" }));
    expect(onDownload).toHaveBeenCalled();
  });
});
