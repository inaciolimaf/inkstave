import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ fetchProposal: vi.fn() }));
vi.mock("./api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
import { toast } from "sonner";

import type { DocumentBridge } from "./types";
import { proposal, render } from "./test-helpers";

afterEach(() => vi.clearAllMocks());

describe("DiffReviewDialog (apply toasts)", () => {
  it("gates the success toast on the apply outcome and gives a phase result (#190)", async () => {
    api.fetchProposal.mockResolvedValue(proposal());
    render();
    await screen.findByText("main.tex");
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    const confirm = await screen.findByRole("alertdialog");
    await userEvent.click(within(confirm).getByRole("button", { name: "Apply" }));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("Changes applied to your document."),
    );
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("renders a distinct error summary and a toast.error when a file fails to apply (#190/AC3)", async () => {
    api.fetchProposal.mockResolvedValue(proposal());
    const bridge: DocumentBridge = {
      readContent: vi.fn(async () => "a\nb\nc\nd\n"),
      applyContent: vi.fn(async () => {
        throw new Error("write blocked");
      }),
    };
    render(bridge);
    await screen.findByText("main.tex");
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    const confirm = await screen.findByRole("alertdialog");
    await userEvent.click(within(confirm).getByRole("button", { name: "Apply" }));

    expect(await screen.findByText("Some changes could not be applied")).toBeInTheDocument();
    expect(screen.getByText(/write blocked/)).toBeInTheDocument();
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Some changes couldn’t be applied."),
    );
    expect(toast.success).not.toHaveBeenCalled();
  });
});
