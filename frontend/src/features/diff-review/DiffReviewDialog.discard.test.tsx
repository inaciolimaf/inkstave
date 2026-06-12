import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ fetchProposal: vi.fn() }));
vi.mock("./api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import { proposal, render } from "./test-helpers";

afterEach(() => vi.clearAllMocks());

describe("DiffReviewDialog (discard guard)", () => {
  it("guards dismissal: Escape with pending decisions opens discard confirm (#191/AC1)", async () => {
    api.fetchProposal.mockResolvedValue(proposal());
    const { onOpenChange } = render();
    await screen.findByText("main.tex");

    await userEvent.keyboard("{Escape}");
    expect(await screen.findByText("Discard your review?")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();

    // Cancel keeps the dialog open.
    await userEvent.click(screen.getByRole("button", { name: "Keep reviewing" }));
    await waitFor(() =>
      expect(screen.queryByText("Discard your review?")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("main.tex")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();

    // Re-trigger and confirm -> closes.
    await userEvent.keyboard("{Escape}");
    await screen.findByText("Discard your review?");
    await userEvent.click(screen.getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("passes dismissal through once changes are applied (no pending decisions) (#191/AC1)", async () => {
    api.fetchProposal.mockResolvedValue(proposal());
    const { onOpenChange } = render();
    await screen.findByText("main.tex");
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    const confirm = await screen.findByRole("alertdialog");
    await userEvent.click(within(confirm).getByRole("button", { name: "Apply" }));
    await screen.findByText("Changes applied");

    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(screen.queryByText("Discard your review?")).not.toBeInTheDocument();
  });
});
