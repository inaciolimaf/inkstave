import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PdfPageText } from "./PdfPageText";
import { renderPageText, type PdfDocument } from "./pdfjs";

vi.mock("./pdfjs", () => ({ renderPageText: vi.fn() }));

const render_ = vi.mocked(renderPageText);
const page = {};
const pdf = { getPage: vi.fn(async () => page) } as unknown as PdfDocument;

describe("PdfPageText", () => {
  beforeEach(() => {
    render_.mockReset();
  });

  it("lays the page's text out at the page's scale", async () => {
    render_.mockReturnValue(vi.fn());
    render(<PdfPageText pdf={pdf} pageNumber={1} scale={1.5} />);
    const layer = screen.getByTestId("pdf-text-layer");
    await waitFor(() => expect(render_).toHaveBeenCalledWith(page, layer, 1.5));
    expect(layer.style.getPropertyValue("--scale-factor")).toBe("1.5");
  });

  it("stops the old text when the zoom changes", async () => {
    const cancel = vi.fn();
    render_.mockReturnValue(cancel);
    const { rerender } = render(<PdfPageText pdf={pdf} pageNumber={1} scale={1} />);
    await waitFor(() => expect(render_).toHaveBeenCalledTimes(1));
    rerender(<PdfPageText pdf={pdf} pageNumber={1} scale={2} />);
    expect(cancel).toHaveBeenCalled();
    await waitFor(() => expect(render_).toHaveBeenCalledTimes(2));
  });
});
