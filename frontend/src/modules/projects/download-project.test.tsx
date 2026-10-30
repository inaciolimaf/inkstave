import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { downloadProjectZip } from "./api";
import { ProjectTable } from "./project-table";
import type { Project } from "./types";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

// Keep the real sanitize; only stub the DOM-touching trigger and the API client.
const getBytes = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api-client", () => ({ apiClient: { getBytes } }));
const trigger = vi.hoisted(() => vi.fn());
vi.mock("@/lib/download", async (orig) => ({
  ...(await orig<typeof import("@/lib/download")>()),
  triggerBrowserDownload: trigger,
}));

const project: Project = {
  id: "p1",
  name: "My Paper",
  ownerId: "u",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
};

afterEach(() => vi.clearAllMocks());

describe("downloadProjectZip", () => {
  it("fetches export.zip and triggers a download with a sanitized .zip filename", async () => {
    getBytes.mockResolvedValue(new ArrayBuffer(8));
    await downloadProjectZip("p1", 'My "Paper"');
    expect(getBytes).toHaveBeenCalledWith("/api/v1/projects/p1/export.zip");
    const [blob, filename] = trigger.mock.calls[0];
    expect((blob as Blob).type).toBe("application/zip");
    expect(filename).toBe("My Paper.zip");
  });
});

describe("RowActionsMenu download item", () => {
  function setup() {
    return renderWithProviders(
      <ProjectTable projects={[project]} onOpen={vi.fn()} onRename={vi.fn()} onDelete={vi.fn()} />,
    );
  }

  it("offers a Download as .zip item that fetches the archive", async () => {
    getBytes.mockResolvedValue(new ArrayBuffer(4));
    setup();
    await userEvent.click(screen.getByRole("button", { name: "Project actions" }));
    const item = await screen.findByRole("menuitem", { name: "Download as .zip" });
    await userEvent.click(item);
    await waitFor(() => expect(getBytes).toHaveBeenCalledWith("/api/v1/projects/p1/export.zip"));
    expect(trigger).toHaveBeenCalled();
  });

  it("surfaces a toast when the download fails", async () => {
    getBytes.mockRejectedValue(new Error("boom"));
    setup();
    await userEvent.click(screen.getByRole("button", { name: "Project actions" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Download as .zip" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Could not download the project"));
  });
});
