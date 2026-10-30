import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { ImportUploadError, type ProjectImport } from "./api";
import { ImportProjectDialog } from "./import-project-dialog";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const api = vi.hoisted(() => ({
  importProjectZip: vi.fn(),
  getImportStatus: vi.fn(),
  deleteProject: vi.fn(),
}));
vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, ...api };
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

function zip(name = "paper.zip"): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type: "application/zip" });
}

beforeEach(() => {
  api.importProjectZip.mockReset();
  api.getImportStatus.mockReset();
  api.deleteProject.mockReset();
  toast.success.mockClear();
});
afterEach(() => vi.restoreAllMocks());

describe("ImportProjectDialog", () => {
  it("disables submit until a .zip is chosen", () => {
    renderWithProviders(<ImportProjectDialog open onOpenChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
    expect(screen.getByLabelText("Project archive (.zip)")).toHaveAttribute("accept", ".zip");
  });

  it("uploads, shows the importing state, and closes + toasts on success", async () => {
    api.importProjectZip.mockResolvedValue(row({ status: "queued" }));
    api.getImportStatus.mockResolvedValue(row({ status: "success" }));
    const onOpenChange = vi.fn();
    renderWithProviders(<ImportProjectDialog open onOpenChange={onOpenChange} />);

    await userEvent.upload(screen.getByLabelText("Project archive (.zip)"), zip());
    await userEvent.click(screen.getByRole("button", { name: "Import" }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(toast.success).toHaveBeenCalledWith("Project imported");
    expect(api.importProjectZip).toHaveBeenCalledOnce();
  });

  it("maps an error_type to a friendly message and keeps the dialog open", async () => {
    api.importProjectZip.mockRejectedValue(new ImportUploadError(413, "zip_too_large", "big"));
    const onOpenChange = vi.fn();
    renderWithProviders(<ImportProjectDialog open onOpenChange={onOpenChange} />);

    await userEvent.upload(screen.getByLabelText("Project archive (.zip)"), zip());
    await userEvent.click(screen.getByRole("button", { name: "Import" }));

    expect(await screen.findByText("This archive is too large to import.")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it("offers to delete the empty project after a post-upload failure", async () => {
    api.importProjectZip.mockResolvedValue(row({ status: "queued" }));
    api.getImportStatus.mockResolvedValue(row({ status: "failure", errorType: "invalid_zip" }));
    api.deleteProject.mockResolvedValue(undefined);
    renderWithProviders(<ImportProjectDialog open onOpenChange={vi.fn()} />);

    await userEvent.upload(screen.getByLabelText("Project archive (.zip)"), zip());
    await userEvent.click(screen.getByRole("button", { name: "Import" }));

    const del = await screen.findByRole("button", { name: "Delete the empty project" });
    await userEvent.click(del);
    await waitFor(() => expect(api.deleteProject).toHaveBeenCalledWith("proj-1"));
  });
});
