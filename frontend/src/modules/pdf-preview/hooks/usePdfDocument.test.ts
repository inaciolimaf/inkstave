import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { getCompilePdf } from "../api";
import { loadPdfDocument } from "../pdfjs";
import { usePdfDocument } from "./usePdfDocument";

vi.mock("../api", () => ({ getCompilePdf: vi.fn() }));
vi.mock("../pdfjs", () => ({ loadPdfDocument: vi.fn() }));

const getPdf = getCompilePdf as Mock;
const load = loadPdfDocument as Mock;

function fakeDoc(numPages: number) {
  return { numPages, destroy: vi.fn().mockResolvedValue(undefined) };
}

beforeEach(() => {
  getPdf.mockReset();
  load.mockReset();
});
afterEach(() => vi.clearAllMocks());

describe("usePdfDocument", () => {
  it("loads the PDF bytes from the right compile and exposes numPages", async () => {
    const bytes = new ArrayBuffer(8);
    getPdf.mockResolvedValue(bytes);
    load.mockResolvedValue(fakeDoc(3));

    const { result } = renderHook(() => usePdfDocument("p1", "c1"));

    await waitFor(() => expect(result.current.pdf).not.toBeNull());
    expect(getPdf).toHaveBeenCalledWith("p1", "c1");
    expect(load).toHaveBeenCalledWith(bytes);
    expect(result.current.numPages).toBe(3);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("does nothing without a compile id", () => {
    const { result } = renderHook(() => usePdfDocument("p1", null));
    expect(getPdf).not.toHaveBeenCalled();
    expect(result.current.pdf).toBeNull();
    expect(result.current.numPages).toBe(0);
  });

  it("destroys the previous document when the compile changes", async () => {
    const first = fakeDoc(1);
    const second = fakeDoc(2);
    getPdf.mockResolvedValue(new ArrayBuffer(8));
    load.mockResolvedValueOnce(first).mockResolvedValueOnce(second);

    const { result, rerender } = renderHook(({ id }) => usePdfDocument("p1", id), {
      initialProps: { id: "c1" },
    });
    await waitFor(() => expect(result.current.pdf).toBe(first));

    rerender({ id: "c2" });
    await waitFor(() => expect(result.current.pdf).toBe(second));
    expect(first.destroy).toHaveBeenCalled();
  });

  it("surfaces a load error", async () => {
    getPdf.mockResolvedValue(new ArrayBuffer(8));
    load.mockRejectedValue(new Error("bad pdf"));
    const { result } = renderHook(() => usePdfDocument("p1", "c1"));
    await waitFor(() => expect(result.current.error).toBe("bad pdf"));
    expect(result.current.pdf).toBeNull();
  });

  it("destroys the document on unmount", async () => {
    const doc = fakeDoc(1);
    getPdf.mockResolvedValue(new ArrayBuffer(8));
    load.mockResolvedValue(doc);
    const { result, unmount } = renderHook(() => usePdfDocument("p1", "c1"));
    await waitFor(() => expect(result.current.pdf).toBe(doc));
    act(() => unmount());
    expect(doc.destroy).toHaveBeenCalled();
  });
});
