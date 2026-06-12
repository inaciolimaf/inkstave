import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ImportUploadError, type ProjectImport } from "./api";
import { useImportProject } from "./use-import-project";

const api = vi.hoisted(() => ({
  importProjectZip: vi.fn(),
  getImportStatus: vi.fn(),
}));

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, importProjectZip: api.importProjectZip, getImportStatus: api.getImportStatus };
});

const row = (over: Partial<ProjectImport> = {}): ProjectImport => ({
  importId: "imp-1",
  projectId: "proj-1",
  status: "queued",
  entriesTotal: null,
  entriesImported: null,
  errorType: null,
  errorMessage: null,
  ...over,
});

beforeEach(() => {
  api.importProjectZip.mockReset();
  api.getImportStatus.mockReset();
});
afterEach(() => vi.restoreAllMocks());

describe("useImportProject", () => {
  it("walks idle → uploading → processing → done on success", async () => {
    api.importProjectZip.mockImplementation(
      async (_f: File, _n: string | undefined, onProgress?: (x: number) => void) => {
        onProgress?.(0.4);
        return row({ status: "queued" });
      },
    );
    api.getImportStatus.mockResolvedValue(row({ status: "success" }));
    const onSuccess = vi.fn();

    const { result } = renderHook(() => useImportProject(onSuccess));
    expect(result.current.state.phase).toBe("idle");

    await act(async () => {
      await result.current.start(new File(["x"], "p.zip"), "Name");
    });

    await waitFor(() => expect(result.current.state.phase).toBe("done"));
    expect(onSuccess).toHaveBeenCalledWith("proj-1");
  });

  it("transitions to failed with the error_type when the upload is rejected", async () => {
    api.importProjectZip.mockRejectedValue(new ImportUploadError(415, "invalid_zip", "bad"));
    const { result } = renderHook(() => useImportProject(vi.fn()));

    await act(async () => {
      await result.current.start(new File(["x"], "p.zip"));
    });

    expect(result.current.state.phase).toBe("failed");
    expect(result.current.state.errorType).toBe("invalid_zip");
  });

  it("transitions to failed when the import job ends in failure", async () => {
    api.importProjectZip.mockResolvedValue(row({ status: "queued" }));
    api.getImportStatus.mockResolvedValue(row({ status: "failure", errorType: "zip_slip" }));
    const { result } = renderHook(() => useImportProject(vi.fn()));

    await act(async () => {
      await result.current.start(new File(["x"], "p.zip"));
    });

    await waitFor(() => expect(result.current.state.phase).toBe("failed"));
    expect(result.current.state.errorType).toBe("zip_slip");
  });

  it("reset returns the machine to idle", async () => {
    api.importProjectZip.mockRejectedValue(new ImportUploadError(400, "generic", "x"));
    const { result } = renderHook(() => useImportProject(vi.fn()));
    await act(async () => {
      await result.current.start(new File(["x"], "p.zip"));
    });
    expect(result.current.state.phase).toBe("failed");
    act(() => result.current.reset());
    expect(result.current.state.phase).toBe("idle");
  });
});
