import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ fetchProposal: vi.fn() }));
vi.mock("./api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import { createYDocBridge } from "./crdt-apply";
import { proposal, render } from "./test-helpers";

afterEach(() => vi.clearAllMocks());

describe("DiffReviewDialog (load & badges)", () => {
  it("loads the proposal and renders the file diff (AC1)", async () => {
    api.fetchProposal.mockResolvedValue(proposal());
    render();
    expect(await screen.findByText("main.tex")).toBeInTheDocument();
    expect(screen.getByText("2/2 accepted")).toBeInTheDocument();
    expect(screen.getAllByRole("switch")).toHaveLength(2);
  });

  it("shows an error state with retry when loading fails (AC10)", async () => {
    api.fetchProposal.mockRejectedValue(new Error("boom"));
    render();
    expect(await screen.findByText(/Couldn’t load the proposal/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows an empty state for a proposal with no files", async () => {
    api.fetchProposal.mockResolvedValue({ ...proposal(), files: [] });
    render();
    expect(await screen.findByText("This proposal has no changes.")).toBeInTheDocument();
  });

  it("labels new-file and deleted files with a badge (#193/AC6)", async () => {
    api.fetchProposal.mockResolvedValue({
      ...proposal(),
      files: [
        { path: "new.tex", docId: "n", baseVersion: "0", isNewFile: true, hunks: [] },
        { path: "old.tex", docId: "o", baseVersion: "0", isDeletion: true, hunks: [] },
      ],
    });
    render(createYDocBridge({ "new.tex": "", "old.tex": "x\n" }));
    expect(await screen.findByText("New file")).toBeInTheDocument();
    expect(screen.getByText("Deleted")).toBeInTheDocument();
  });
});
