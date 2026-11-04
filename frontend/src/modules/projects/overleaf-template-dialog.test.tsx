import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { type ProjectImport } from "./api";
import { OVERLEAF_TEMPLATES_URL, OverleafTemplateDialog } from "./overleaf-template-dialog";

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
  source: "overleaf_template",
  compatReport: null,
  reportSeenAt: null,
  entriesTotal: null,
  entriesImported: null,
  errorType: null,
  errorMessage: null,
  ...over,
});

function zip(name = "template.zip"): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type: "application/zip" });
}

beforeEach(() => {
  api.importProjectZip.mockReset();
  api.getImportStatus.mockReset();
  api.deleteProject.mockReset();
});
afterEach(() => vi.restoreAllMocks());

describe("OverleafTemplateDialog", () => {
  it("shows the three steps and an external link that opens in a new tab", () => {
    renderWithProviders(<OverleafTemplateDialog open onOpenChange={vi.fn()} />);

    expect(screen.getByText("Find a template on Overleaf and open it.")).toBeInTheDocument();
    expect(
      screen.getByText("In the template, choose Menu, then Download, then Source. This saves a .zip."),
    ).toBeInTheDocument();
    expect(screen.getByText("Drop that .zip here, or choose it.")).toBeInTheDocument();

    const link = screen.getByRole("link", { name: /Browse Overleaf templates/ });
    expect(link).toHaveAttribute("href", OVERLEAF_TEMPLATES_URL);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(OVERLEAF_TEMPLATES_URL).toBe("https://www.overleaf.com/latex/templates");
  });

  it("uploads the chosen zip as an Overleaf template and offers Open project when done", async () => {
    api.importProjectZip.mockResolvedValue(row());
    api.getImportStatus.mockResolvedValue(row({ status: "success" }));
    renderWithProviders(<OverleafTemplateDialog open onOpenChange={vi.fn()} />);

    await userEvent.upload(screen.getByLabelText("Drop the .zip here, or choose a file"), zip());

    await waitFor(() => expect(api.importProjectZip).toHaveBeenCalledOnce());
    const args = api.importProjectZip.mock.calls[0];
    expect(args[0]).toBeInstanceOf(File);
    expect(args[3]).toBe("overleaf_template");
    expect(await screen.findByRole("button", { name: "Open project" })).toBeInTheDocument();
  });

  it("maps a failed template import to its message and keeps the dialog open", async () => {
    const { ImportUploadError } = await vi.importActual<typeof import("./api")>("./api");
    api.importProjectZip.mockRejectedValue(new ImportUploadError(422, "zip_empty", "empty"));
    const onOpenChange = vi.fn();
    renderWithProviders(<OverleafTemplateDialog open onOpenChange={onOpenChange} />);

    await userEvent.upload(screen.getByLabelText("Drop the .zip here, or choose a file"), zip());

    expect(await screen.findByText("This archive has no importable files.")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
