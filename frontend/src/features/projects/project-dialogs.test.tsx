import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { CreateProjectDialog, DeleteProjectDialog, RenameProjectDialog } from "./project-dialogs";
import type { Project } from "./types";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const project: Project = {
  id: "p1",
  name: "Existing",
  ownerId: "u",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
};

afterEach(() => vi.restoreAllMocks());

describe("CreateProjectDialog", () => {
  it("disables submit for an empty or whitespace name and shows a message", async () => {
    renderWithProviders(<CreateProjectDialog open onOpenChange={vi.fn()} />);
    const submit = screen.getByRole("button", { name: "Create" });
    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Project name"), "   ");
    expect(await screen.findByText("Project name is required.")).toBeInTheDocument();
    expect(submit).toBeDisabled();
  });

  it("submits a trimmed name and closes on success", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "new",
          name: "Hello",
          owner_id: "u",
          root_doc_id: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    const onOpenChange = vi.fn();
    renderWithProviders(<CreateProjectDialog open onOpenChange={onOpenChange} />);

    await userEvent.type(screen.getByLabelText("Project name"), "  Hello  ");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    const [, init] = fetchMock.mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ name: "Hello" });
    expect(toast.success).toHaveBeenCalledWith("Project created");
  });
});

describe("RenameProjectDialog", () => {
  it("pre-fills the input with the current project name on open", async () => {
    renderWithProviders(<RenameProjectDialog open onOpenChange={vi.fn()} project={project} />);
    expect(await screen.findByDisplayValue("Existing")).toBeInTheDocument();
  });

  it("cancels on Esc without renaming", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const onOpenChange = vi.fn();
    renderWithProviders(<RenameProjectDialog open onOpenChange={onOpenChange} project={project} />);

    await screen.findByDisplayValue("Existing");
    await userEvent.keyboard("{Escape}");

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uses the rename title and a Save confirm button", async () => {
    renderWithProviders(<RenameProjectDialog open onOpenChange={vi.fn()} project={project} />);
    expect(await screen.findByRole("heading", { name: "Rename project" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });
});

describe("DeleteProjectDialog", () => {
  beforeEach(() => toast.error.mockClear());

  it("shows the project name, focuses Cancel, and closes on Esc without deleting", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const onOpenChange = vi.fn();
    renderWithProviders(<DeleteProjectDialog open onOpenChange={onOpenChange} project={project} />);

    expect(screen.getByText(/Delete .*Existing.*\?/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus());

    await userEvent.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
