import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import { codeToPdf, pdfToCode } from "../synctex";
import { useSyncTex } from "./useSyncTex";

vi.mock("../synctex", () => ({ codeToPdf: vi.fn(), pdfToCode: vi.fn() }));
const toast = vi.hoisted(() => ({ message: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const fwd = codeToPdf as Mock;
const inv = pdfToCode as Mock;
const BOX = { page: 2, h: 100, v: 200, width: 4, height: 1, depth: 0 };

afterEach(() => {
  fwd.mockReset();
  inv.mockReset();
  toast.message.mockReset();
  toast.error.mockReset();
});

describe("useSyncTex forward", () => {
  it("sets a pdf target from the first box", async () => {
    fwd.mockResolvedValue({ ok: true, value: { boxes: [BOX] } });
    const { result } = renderHook(() => useSyncTex("p1", "c1"));
    await act(async () => {
      await result.current.syncFromSource("main.tex", 10);
    });
    expect(fwd).toHaveBeenCalledWith("p1", { file: "main.tex", line: 10, compileId: "c1" });
    expect(result.current.pdfTarget).toMatchObject({ page: 2, box: BOX });
  });

  it("bumps the nonce on each forward sync", async () => {
    fwd.mockResolvedValue({ ok: true, value: { boxes: [BOX] } });
    const { result } = renderHook(() => useSyncTex("p1", "c1"));
    await act(async () => {
      await result.current.syncFromSource("main.tex", 10);
    });
    const first = result.current.pdfTarget?.nonce;
    await act(async () => {
      await result.current.syncFromSource("main.tex", 10);
    });
    expect(result.current.pdfTarget?.nonce).toBe((first ?? 0) + 1);
  });

  it("toasts synctex_unavailable and sets no target", async () => {
    fwd.mockResolvedValue({ ok: false, reason: "synctex_unavailable" });
    const { result } = renderHook(() => useSyncTex("p1", "c1"));
    await act(async () => {
      await result.current.syncFromSource("main.tex", 10);
    });
    expect(toast.message).toHaveBeenCalledWith("SyncTeX data not available for this compile");
    expect(result.current.pdfTarget).toBeNull();
  });

  it("toasts when there are no boxes", async () => {
    fwd.mockResolvedValue({ ok: true, value: { boxes: [] } });
    const { result } = renderHook(() => useSyncTex("p1", "c1"));
    await act(async () => {
      await result.current.syncFromSource("main.tex", 10);
    });
    expect(toast.message).toHaveBeenCalledWith("No matching location");
    expect(result.current.pdfTarget).toBeNull();
  });
});

describe("useSyncTex inverse", () => {
  it("returns the resolved location", async () => {
    inv.mockResolvedValue({ ok: true, value: { file: "main.tex", line: 10, column: null } });
    const { result } = renderHook(() => useSyncTex("p1", "c1"));
    let location: unknown;
    await act(async () => {
      location = await result.current.syncFromPdf(1, 100, 200);
    });
    expect(inv).toHaveBeenCalledWith("p1", { page: 1, h: 100, v: 200, compileId: "c1" });
    expect(location).toEqual({ file: "main.tex", line: 10, column: null });
  });

  it("toasts and returns null on no_match", async () => {
    inv.mockResolvedValue({ ok: false, reason: "no_match" });
    const { result } = renderHook(() => useSyncTex("p1", "c1"));
    let location: unknown = "x";
    await act(async () => {
      location = await result.current.syncFromPdf(1, 1, 1);
    });
    expect(location).toBeNull();
    await waitFor(() => expect(toast.message).toHaveBeenCalledWith("No matching location"));
  });
});
